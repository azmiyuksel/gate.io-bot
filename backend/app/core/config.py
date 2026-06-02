from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Gate.io Capital Preservation Bot"
    environment: str = "local"
    secret_key: str = Field(default="change-me")
    # Access tokens are short-lived so role changes / revocation propagate quickly.
    access_token_expire_minutes: int = 15
    # Refresh tokens are long-lived but server-tracked and individually revocable.
    refresh_token_expire_days: int = 7
    # Failed logins allowed per client/email window before throttling kicks in.
    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 300

    database_url: str = "postgresql+psycopg://gatebot:gatebot@localhost:5432/gatebot"
    redis_url: str = "redis://localhost:6379/0"

    # Comma-separated list of allowed CORS origins for the browser dashboard.
    cors_origins: str = "http://localhost:3000"

    # Max inline CSV upload size (backtests / walk-forward) in bytes.
    max_csv_upload_bytes: int = 10 * 1024 * 1024
    # Hard cap on list/candle `limit` query params to bound memory and API abuse.
    max_query_limit: int = 1000

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
    # Max age (seconds) of an equity snapshot before it is considered stale and
    # unsafe to size new positions against. Trading runs every 15m, so allow ~2 cycles.
    max_equity_staleness_seconds: int = 1800
    gateio_ws_url: str = "wss://api.gateio.ws/ws/v4/"
    market_data_interval: str = "1h"

    # --- Market Data Quality ---
    # Single-candle move beyond this fraction is flagged as a spike (0.01-0.10 typical).
    mdq_spike_threshold_pct: float = 0.10
    # Z-score above which a price/volume move is treated as anomalous.
    mdq_zscore_threshold: float = 5.0
    # Volume spike multiple over rolling mean.
    mdq_volume_spike_multiple: float = 8.0
    # Liquidity drop: volume below this fraction of rolling mean.
    mdq_liquidity_drop_pct: float = 0.10
    # Cross-exchange price divergence tolerance.
    mdq_cross_exchange_threshold_pct: float = 0.01
    # Spike handling mode: flag | smooth | ignore
    mdq_spike_mode: str = "flag"
    # Block trading when feed health score falls below INVALID threshold.
    mdq_pause_on_invalid: bool = True
    # Position-size multiplier applied while the data feed is DEGRADED (de-risk).
    mdq_degraded_risk_multiplier: float = 0.5
    # Enable the optional Isolation Forest ML anomaly layer.
    mdq_enable_ml: bool = True

    # --- Strategy Research Lab ---
    # Production promotion gate.
    research_min_sharpe: float = 1.0
    research_max_drawdown: float = 0.20        # positive magnitude
    research_min_stability: float = 0.5
    research_min_consistency: float = 0.5
    research_min_trades: int = 20
    # Walk-forward windows used during evaluation.
    research_wf_windows: int = 4
    # Population size per research-loop generation.
    research_population: int = 12
    research_survivors: int = 4

    # --- Auto Learning & Continuous Evolution ---
    learning_enabled: bool = True
    # Candidates evolved per learning cycle.
    learning_population: int = 8
    # Promotion gate (human approval still required afterwards).
    learning_gate_min_sharpe: float = 1.5
    learning_gate_min_profit_factor: float = 1.3
    learning_gate_min_consistency: float = 0.60
    learning_gate_max_ruin: float = 0.20
    # Minimum ranking score (0-100) to even create a promotion request.
    learning_min_ranking: float = 60.0

    @property
    def symbols(self) -> list[str]:
        return [symbol.strip() for symbol in self.trading_symbols.split(",") if symbol.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in ("production", "prod", "staging")

    def validate_runtime_secrets(self) -> list[str]:
        """Enforce strong secrets outside local/dev. Returns non-fatal warnings.

        Raises RuntimeError for fatal misconfiguration in production-like
        environments (a forgeable JWT secret is a full auth bypass).
        """
        warnings: list[str] = []
        weak_secret = self.secret_key in ("", "change-me")
        if weak_secret:
            if self.is_production:
                raise RuntimeError(
                    "SECRET_KEY must be set to a strong, unique value in "
                    f"environment='{self.environment}'."
                )
            warnings.append("SECRET_KEY is the insecure default ('change-me').")
        if not self.fernet_key:
            warnings.append("FERNET_KEY is unset; stored API secrets are not encrypted.")
        return warnings


@lru_cache
def get_settings() -> Settings:
    return Settings()
