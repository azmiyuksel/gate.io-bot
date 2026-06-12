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
    # Stablecoins counted as cash at par (not marked to market) in equity.
    stablecoins: str = "USDT,USDC,DAI,TUSD,FDUSD"

    # Opportunity cost of idle capital: the ~risk-free yield idle USDT could earn
    # (e.g. exchange lending/Earn). The strategy must beat this hurdle to add value.
    annual_risk_free_rate: float = 0.04

    # Graded de-risking: shrink size as account drawdown approaches the max.
    drawdown_derisk_enabled: bool = True
    drawdown_derisk_floor: float = 0.0

    # --- Stablecoin (quote) depeg monitoring ---
    # Pair used to proxy the quote stablecoin's peg (drift from 1.0).
    quote_depeg_reference_pair: str = "USDC_USDT"
    quote_depeg_threshold_pct: float = 0.01  # 1% drift from parity
    quote_depeg_halt: bool = True            # pause new entries while depegged

    # --- Volatility targeting (opt-in): scale size inversely to volatility ---
    vol_targeting_enabled: bool = False
    vol_target_atr_pct: float = 0.02          # target ATR as a fraction of price
    vol_target_min_multiplier: float = 0.25
    vol_target_max_multiplier: float = 1.5

    # --- Live strategy entry thresholds (tunable per market) ---
    strategy_rsi_threshold: float = 35.0
    strategy_ema20_distance_pct: float = 0.01
    # Max 24h range as a fraction of price before an entry is rejected. 0.08 is
    # tight for crypto; raise per pair to allow entries in normal volatility.
    strategy_max_24h_range_pct: float = 0.08
    # Default trailing-stop distance (used when StrategySettings is missing).
    strategy_trailing_stop_pct: float = 0.01
    # Number of candles that represent a "daily" range (depends on candle interval).
    strategy_daily_range_candles: int = 24
    trading_symbols: str = "BTC_USDT,ETH_USDT"
    # Minimum volume ratio: reject entries when current volume is below this fraction
    # of the recent average volume (e.g., 0.5 = 50% of average). Prevents entries
    # on illiquid bars that are hard to exit at fair price.
    strategy_min_volume_ratio: float = 0.5
    # Maximum absolute dollar loss per trade as a fraction of equity. This provides
    # a hard cap on any single trade's risk, protecting against flash crashes where
    # the stop-loss distance is wide but the trade size is large.
    max_risk_per_trade_pct: float = 0.02
    # Maximum total portfolio exposure as a fraction of equity. Prevents over-allocation
    # when max_open_positions is set too high.
    max_total_exposure_pct: float = 0.30

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

    # --- Portfolio ---
    # Rebalance trigger drawdown threshold.
    portfolio_rebalance_drawdown_pct: float = 0.05
    # Rebalance schedule intervals (days).
    portfolio_rebalance_weekly_days: int = 7
    portfolio_rebalance_monthly_days: int = 30
    # Correlation threshold for flagging high-correlation pairs.
    portfolio_correlation_threshold: float = 0.8
    # Max candles for correlation calculation.
    portfolio_correlation_limit: int = 500
    # Stress test shock magnitudes.
    stress_market_crash_pct: float = 0.30
    stress_flash_crash_major: float = 0.50
    stress_flash_crash_alt: float = 0.70
    stress_high_vol_pct: float = 0.15
    stress_correlation_spike_pct: float = 0.20

    # --- Backtest ---
    backtest_monte_carlo_scenarios: int = 1000
    # VaR lookback: number of bars used for historical Value-at-Risk.
    # 200 ≈ 8 days (hourly); 252 ≈ 1 year (daily). Higher = more stable tail estimate.
    var_lookback: int = 500
    # Breakeven stop: move stop-loss to entry price when unrealized profit
    # reaches this fraction of the entry price (0.02 = 2% profit → BE stop).
    breakeven_stop_trigger_pct: float = 0.02
    # Estimated round-trip trading cost (taker fees + spread + slippage)
    # used when evaluating whether a rebalance is worth executing.
    rebalance_cost_bps: float = 10.0  # 10 bps = 0.10%

    # --- Strategy Health Risk Adjuster ---
    health_drift_tier_low: float = 0.3
    health_drift_tier_mid: float = 0.5
    health_drift_tier_high: float = 0.7
    health_risk_mult_low: float = 1.0
    health_risk_mult_mid: float = 0.7
    health_risk_mult_high: float = 0.4
    health_risk_mult_paused: float = 0.0

    # --- Execution Quality ---
    eq_default_volatility: float = 0.015
    eq_default_spread: float = 0.0002
    eq_latency_zscore_threshold: float = 3.0
    eq_critical_slippage_pct: float = 0.005
    eq_partial_fill_explosion_threshold: int = 4

    # --- Portfolio Allocator ---
    alloc_weight_strategy: float = 0.40
    alloc_weight_risk_adj: float = 0.30
    alloc_weight_correlation: float = 0.20
    alloc_weight_stability: float = 0.10
    alloc_dd_tier_high: float = 0.15
    alloc_dd_tier_mid: float = 0.08
    alloc_dd_tier_low: float = 0.03
    alloc_dd_scale_high: float = 0.30
    alloc_dd_scale_mid: float = 0.60
    alloc_dd_scale_low: float = 0.85

    @property
    def symbols(self) -> list[str]:
        return [symbol.strip() for symbol in self.trading_symbols.split(",") if symbol.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def stablecoin_set(self) -> set[str]:
        return {s.strip().upper() for s in self.stablecoins.split(",") if s.strip()}

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in ("production", "prod", "staging")

    def validate_runtime_secrets(self) -> list[str]:
        """Enforce strong secrets outside local/dev. Returns non-fatal warnings.

        Raises RuntimeError for fatal misconfiguration in production-like
        environments (a forgeable JWT secret is a full auth bypass, and unencrypted
        API secrets on disk are a credential-theft risk).
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
            if self.is_production:
                raise RuntimeError(
                    "FERNET_KEY must be set in production — stored API secrets "
                    "would otherwise be persisted in plain text."
                )
            warnings.append("FERNET_KEY is unset; stored API secrets are not encrypted.")
        if self.is_production:
            for origin in self.cors_origin_list:
                if "localhost" in origin or "127.0.0.1" in origin:
                    raise RuntimeError(
                        f"CORS origin '{origin}' is not allowed in production. "
                        f"Set CORS_ORIGINS to your production domain."
                    )
        return warnings


@lru_cache
def get_settings() -> Settings:
    return Settings()
