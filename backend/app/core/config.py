from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Gate.io Capital Preservation Bot"
    environment: str = "local"
    secret_key: str = Field(default="change-me")
    access_token_expire_minutes: int = 60

    database_url: str = "postgresql+psycopg://gatebot:gatebot@localhost:5432/gatebot"
    redis_url: str = "redis://localhost:6379/0"

    gateio_api_key: str = ""
    gateio_api_secret: str = ""
    gateio_base_url: str = "https://api.gateio.ws/api/v4"
    gateio_requests_per_second: int = 5

    fernet_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    bot_enabled: bool = False
    default_quote_currency: str = "USDT"
    trading_symbols: str = "BTC_USDT,ETH_USDT"

    # Equity used when the exchange balance cannot be fetched (no keys / offline).
    fallback_equity: float = 10000.0
    # Max account drawdown from peak equity before the circuit breaker trips.
    max_account_drawdown_pct: float = 0.15
    gateio_ws_url: str = "wss://api.gateio.ws/ws/v4/"
    market_data_interval: str = "1h"

    @property
    def symbols(self) -> list[str]:
        return [symbol.strip() for symbol in self.trading_symbols.split(",") if symbol.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
