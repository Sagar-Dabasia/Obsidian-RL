"""Typed application settings.

Reads ONLY process environment variables with the OBSIDIAN_ prefix. Deliberately does
not read .env files: this platform needs no credentials, and secrets must never enter
its configuration.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OBSIDIAN_", env_file=None)

    symbol: str = "BTCUSDT"
    interval: str = "15m"

    # Public market-data endpoints (ADR-003). No authenticated endpoint is ever used.
    fapi_base_url: str = "https://fapi.binance.com"
    vision_base_url: str = "https://data.binance.vision"
    ws_base_url: str = "wss://fstream.binance.com/market/ws"

    data_dir: Path = Path("data")
    models_dir: Path = Path("models")
    ledger_path: Path = Path("data") / "ledger.sqlite3"

    request_timeout_s: float = 30.0
    max_retries: int = 5
    max_live_open_lag_ms: int = Field(default=5000, ge=0)


def get_settings() -> Settings:
    return Settings()
