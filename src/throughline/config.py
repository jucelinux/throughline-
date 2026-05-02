"""Runtime configuration via env vars (THROUGHLINE_* prefix)."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="THROUGHLINE_",
        env_file=".env",
        extra="ignore",
    )

    db_path: Path = Field(default=Path(".throughline/state.db"))
    docs_dir: Path = Field(default=Path(".docs"))
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8765)
    debounce_ms: int = Field(default=500)
    log_level: str = Field(default="INFO")
    # DNS rebinding protection allowlist for the StreamableHTTP transport.
    # Empty list disables protection (use only when fronted by a trusted proxy).
    allowed_hosts: list[str] = Field(
        default=["127.0.0.1:*", "localhost:*", "[::1]:*"]
    )


def get_settings() -> Settings:
    return Settings()
