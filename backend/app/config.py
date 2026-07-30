"""Environment-driven settings. Secrets only from env vars."""

from __future__ import annotations

import logging
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("casual_board.config")

# Canonical grok.me web origin for this project (phone UI).
GROK_ME_WEB_ORIGIN = "https://discovery-system.grok.me"

DEFAULT_PROD_CORS = ",".join(
    [
        GROK_ME_WEB_ORIGIN,
        "https://www.discovery-system.grok.me",
    ]
)


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

    # Auth — empty allows open-dev mode (local only; never public)
    api_token: str = Field(default="", alias="CASUAL_BOARD_TOKEN")

    data_dir: Path = Field(default=Path("data"), alias="CASUAL_BOARD_DATA_DIR")

    # CORS — production must list explicit origins (never "*")
    cors_origins: str = Field(
        default="*",
        alias="CASUAL_BOARD_CORS_ORIGINS",
    )

    # Public base URL of THIS API (https://api… or tunnel URL). Used for docs/logs.
    public_base_url: str = Field(default="", alias="CASUAL_BOARD_PUBLIC_BASE_URL")

    # Comma-separated hostnames allowed behind reverse proxy (empty = any in dev)
    trusted_hosts: str = Field(default="", alias="CASUAL_BOARD_TRUSTED_HOSTS")

    # Trust X-Forwarded-Proto / X-Forwarded-For from reverse proxy (Cloudflare, Caddy)
    trust_proxy: bool = Field(default=True, alias="CASUAL_BOARD_TRUST_PROXY")

    enable_pydantic_ai: bool = Field(default=True, alias="CASUAL_BOARD_ENABLE_AI")

    # Fail hard on misconfig when true
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
    def cors_origin_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if not raw:
            return [GROK_ME_WEB_ORIGIN] if self.is_production else ["*"]
        if raw == "*":
            if self.is_production:
                # Never allow wildcard CORS in production
                return [GROK_ME_WEB_ORIGIN]
            return ["*"]
        origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
        # Always include the grok.me app origin in prod lists
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
        return bool(self.api_token.strip())

    @model_validator(mode="after")
    def validate_production(self) -> Settings:
        problems: list[str] = []
        if self.is_production:
            if not self.api_token.strip():
                problems.append(
                    "CASUAL_BOARD_TOKEN is required in production (open-dev forbidden)"
                )
            if self.cors_origins.strip() == "*":
                # auto-fix to grok.me list; warn
                object.__setattr__(self, "cors_origins", DEFAULT_PROD_CORS)
                log.warning(
                    "CASUAL_BOARD_CORS_ORIGINS=* replaced with production list: %s",
                    DEFAULT_PROD_CORS,
                )
            if not self.public_base_url.strip():
                problems.append(
                    "CASUAL_BOARD_PUBLIC_BASE_URL should be set in production "
                    "(public https origin of this API, e.g. Cloudflare Tunnel URL)"
                )
            pub = self.public_base_url.strip()
            if pub and not pub.startswith("https://"):
                problems.append(
                    "CASUAL_BOARD_PUBLIC_BASE_URL must be https:// in production"
                )

        if problems:
            msg = "Environment validation failed:\n  - " + "\n  - ".join(problems)
            if self.strict_env or self.is_production:
                # In production always fail; strict_env forces fail in any env
                if self.is_production or self.strict_env:
                    # Allow missing public_base_url as warning-only if only that
                    hard = [
                        p
                        for p in problems
                        if "CASUAL_BOARD_TOKEN" in p or "must be https" in p
                    ]
                    soft = [p for p in problems if p not in hard]
                    for s in soft:
                        log.warning("%s", s)
                    if hard:
                        log.error("%s", msg)
                        raise ValueError(msg)
            else:
                for p in problems:
                    log.warning("%s", p)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


def validate_or_exit() -> Settings:
    """Call at process start; exits non-zero on hard production misconfig."""
    try:
        s = get_settings()
        # Trigger validators by re-reading properties
        _ = s.cors_origin_list
        _ = s.auth_required
        if s.is_production and not s.auth_required:
            log.error("refusing to start: production without CASUAL_BOARD_TOKEN")
            sys.exit(2)
        return s
    except ValueError as e:
        log.error("%s", e)
        sys.exit(2)
