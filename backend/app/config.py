"""Environment-driven settings. Secrets only from env vars — never Vite/browser."""

from __future__ import annotations

import logging
import sys
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("casual_board.config")

GROK_ME_WEB_ORIGIN = "https://discovery-system.grok.me"
DEFAULT_PROD_CORS = ",".join([GROK_ME_WEB_ORIGIN, "https://www.discovery-system.grok.me"])

AiProvider = Literal["none", "function", "openai", "xai"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Casual Board API"
    app_env: str = Field(default="development", alias="CASUAL_BOARD_ENV")
    host: str = Field(default="0.0.0.0", alias="CASUAL_BOARD_HOST")
    port: int = Field(default=8090, alias="CASUAL_BOARD_PORT")
    log_level: str = Field(default="INFO", alias="CASUAL_BOARD_LOG_LEVEL")

    # Owner/admin secret — CLI + approval only. NEVER send to browser / VITE_*.
    api_token: str = Field(default="", alias="CASUAL_BOARD_TOKEN")
    # Bridge worker secret — long-poll + HMAC result signatures. NEVER in browser.
    bridge_token: str = Field(default="", alias="CASUAL_BOARD_BRIDGE_TOKEN")

    data_dir: Path = Field(default=Path("data"), alias="CASUAL_BOARD_DATA_DIR")
    cors_origins: str = Field(default="*", alias="CASUAL_BOARD_CORS_ORIGINS")
    public_base_url: str = Field(default="", alias="CASUAL_BOARD_PUBLIC_BASE_URL")
    trusted_hosts: str = Field(default="", alias="CASUAL_BOARD_TRUSTED_HOSTS")
    trust_proxy: bool = Field(default=True, alias="CASUAL_BOARD_TRUST_PROXY")

    # PydanticAI — explicit provider; "function" is deterministic demo, not a live LLM
    enable_pydantic_ai: bool = Field(default=True, alias="CASUAL_BOARD_ENABLE_AI")
    ai_provider: str = Field(default="auto", alias="CASUAL_BOARD_AI_PROVIDER")
    ai_model: str = Field(default="", alias="CASUAL_BOARD_AI_MODEL")

    strict_env: bool = Field(default=False, alias="CASUAL_BOARD_STRICT_ENV")

    @field_validator("app_env")
    @classmethod
    def normalize_env(cls, v: str) -> str:
        return (v or "development").strip().lower()

    @property
    def is_production(self) -> bool:
        return self.app_env in {"production", "prod", "staging"}

    @property
    def board_path(self) -> Path:
        return self.data_dir / "board.json"

    @property
    def actions_path(self) -> Path:
        return self.data_dir / "actions.jsonl"

    @property
    def jobs_path(self) -> Path:
        return self.data_dir / "jobs.jsonl"

    @property
    def cors_origin_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if not raw:
            return [GROK_ME_WEB_ORIGIN] if self.is_production else ["*"]
        if raw == "*":
            if self.is_production:
                return [GROK_ME_WEB_ORIGIN]
            return ["*"]
        origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
        if self.is_production and GROK_ME_WEB_ORIGIN not in origins:
            origins.append(GROK_ME_WEB_ORIGIN)
        return origins

    @property
    def trusted_host_list(self) -> list[str] | None:
        raw = self.trusted_hosts.strip()
        if not raw:
            return None
        return [h.strip() for h in raw.split(",") if h.strip()]

    @property
    def auth_required(self) -> bool:
        """Owner token required for admin routes. Board reads stay public."""
        return bool(self.api_token.strip())

    @property
    def bridge_auth_required(self) -> bool:
        return bool((self.bridge_token or self.api_token).strip())

    def resolved_ai_provider(self) -> AiProvider:
        """Explicit provider resolution. used_ai is True only for openai|xai live calls."""
        import os

        raw = (self.ai_provider or "auto").strip().lower()
        if raw in {"none", "off", "disabled"}:
            return "none"
        if raw in {"function", "demo", "deterministic"}:
            return "function"
        if raw in {"openai", "xai"}:
            return raw  # type: ignore[return-value]
        # auto
        if not self.enable_pydantic_ai:
            return "none"
        if os.environ.get("XAI_API_KEY"):
            return "xai"
        if os.environ.get("OPENAI_API_KEY"):
            return "openai"
        return "function"

    def resolved_ai_model(self) -> str:
        if self.ai_model.strip():
            return self.ai_model.strip()
        prov = self.resolved_ai_provider()
        if prov == "xai":
            return "openai:grok-2-latest"
        if prov == "openai":
            return "openai:gpt-4o-mini"
        return "function:casual-board-capture"

    @model_validator(mode="after")
    def validate_production(self) -> Settings:
        problems: list[str] = []
        if self.is_production:
            if not self.api_token.strip():
                problems.append("CASUAL_BOARD_TOKEN is required in production")
            if not (self.bridge_token or self.api_token).strip():
                problems.append("CASUAL_BOARD_BRIDGE_TOKEN (or TOKEN) required in production")
            if self.cors_origins.strip() == "*":
                object.__setattr__(self, "cors_origins", DEFAULT_PROD_CORS)
                log.warning("CORS * replaced with %s", DEFAULT_PROD_CORS)
            pub = self.public_base_url.strip()
            if pub and not pub.startswith("https://"):
                problems.append("CASUAL_BOARD_PUBLIC_BASE_URL must be https:// in production")
        hard = [p for p in problems if "TOKEN" in p or "must be https" in p]
        if hard and (self.is_production or self.strict_env):
            raise ValueError("Environment validation failed:\n  - " + "\n  - ".join(hard))
        for p in problems:
            if p not in hard:
                log.warning("%s", p)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


def validate_or_exit() -> Settings:
    try:
        s = get_settings()
        _ = s.cors_origin_list
        if s.is_production and not s.auth_required:
            log.error("refusing to start: production without CASUAL_BOARD_TOKEN")
            sys.exit(2)
        return s
    except ValueError as e:
        log.error("%s", e)
        sys.exit(2)
