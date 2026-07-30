"""Environment-driven settings. Secrets only from env — never VITE_* / browser."""

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
DEFAULT_PROD_CORS = GROK_ME_WEB_ORIGIN

AiProvider = Literal["none", "function", "openai", "xai"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Casual Board API"
    app_env: str = Field(default="development", alias="CASUAL_BOARD_ENV")
    host: str = Field(default="127.0.0.1", alias="CASUAL_BOARD_HOST")
    port: int = Field(default=8090, alias="CASUAL_BOARD_PORT")
    log_level: str = Field(default="INFO", alias="CASUAL_BOARD_LOG_LEVEL")

    # Owner/admin — approvals only. Never browser.
    api_token: str = Field(default="", alias="CASUAL_BOARD_TOKEN")
    # Debian bridge long-poll + HMAC. Never browser.
    bridge_token: str = Field(default="", alias="CASUAL_BOARD_BRIDGE_TOKEN")
    # Browser UI login password (issues short-lived session tokens).
    ui_password: str = Field(default="", alias="CASUAL_BOARD_UI_PASSWORD")
    # HMAC key for session tokens (prefer distinct from owner token).
    session_secret: str = Field(default="", alias="CASUAL_BOARD_SESSION_SECRET")
    session_ttl_s: int = Field(default=3600, alias="CASUAL_BOARD_SESSION_TTL_S")

    data_dir: Path = Field(default=Path("data"), alias="CASUAL_BOARD_DATA_DIR")
    cors_origins: str = Field(
        default=GROK_ME_WEB_ORIGIN,
        alias="CASUAL_BOARD_CORS_ORIGINS",
    )
    public_base_url: str = Field(default="", alias="CASUAL_BOARD_PUBLIC_BASE_URL")
    # Loopback-only API: only trust proxy from local tunnel agent
    trust_proxy: bool = Field(default=True, alias="CASUAL_BOARD_TRUST_PROXY")
    forwarded_allow_ips: str = Field(
        default="127.0.0.1,::1",
        alias="CASUAL_BOARD_FORWARDED_ALLOW_IPS",
    )
    trusted_hosts: str = Field(
        default="api.apidiscoverysolution.uk,127.0.0.1,localhost",
        alias="CASUAL_BOARD_TRUSTED_HOSTS",
    )

    enable_pydantic_ai: bool = Field(default=True, alias="CASUAL_BOARD_ENABLE_AI")
    ai_provider: str = Field(default="function", alias="CASUAL_BOARD_AI_PROVIDER")
    ai_model: str = Field(default="", alias="CASUAL_BOARD_AI_MODEL")
    lease_ttl_s: int = Field(default=60, alias="CASUAL_BOARD_LEASE_TTL_S")
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
    def sqlite_path(self) -> Path:
        return self.data_dir / "casual_board.sqlite3"

    @property
    def cors_origin_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if not raw or raw == "*":
            if self.is_production:
                return [GROK_ME_WEB_ORIGIN]
            # dev: allow local preview + grok.me
            return ["*", GROK_ME_WEB_ORIGIN]
        origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
        if GROK_ME_WEB_ORIGIN not in origins:
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
        return bool(self.api_token.strip()) or self.is_production

    def resolved_ai_provider(self) -> AiProvider:
        import os

        raw = (self.ai_provider or "auto").strip().lower()
        if raw in {"none", "off", "disabled"}:
            return "none"
        if raw in {"function", "demo", "deterministic"}:
            return "function"
        if raw in {"openai", "xai"}:
            return raw  # type: ignore[return-value]
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
        if not self.is_production and not self.strict_env:
            return self
        hard: list[str] = []
        if not self.api_token.strip():
            hard.append("CASUAL_BOARD_TOKEN required")
        if not self.bridge_token.strip():
            hard.append("CASUAL_BOARD_BRIDGE_TOKEN required (must differ from owner token)")
        if self.bridge_token and self.api_token and self.bridge_token == self.api_token:
            hard.append("CASUAL_BOARD_BRIDGE_TOKEN must be distinct from CASUAL_BOARD_TOKEN")
        if not self.ui_password.strip():
            hard.append("CASUAL_BOARD_UI_PASSWORD required for private browser login")
        if not self.session_secret.strip():
            hard.append("CASUAL_BOARD_SESSION_SECRET required")
        if self.cors_origins.strip() == "*":
            object.__setattr__(self, "cors_origins", DEFAULT_PROD_CORS)
        if hard:
            raise ValueError("Environment validation failed:\n  - " + "\n  - ".join(hard))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


def validate_or_exit() -> Settings:
    try:
        s = get_settings()
        _ = s.cors_origin_list
        return s
    except ValueError as e:
        log.error("%s", e)
        sys.exit(2)
