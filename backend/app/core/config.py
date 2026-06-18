from functools import lru_cache

from pydantic import Field, field_validator
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
    # Live engine strategy (mirrors paper). Default is the frequent momentum/breakout
    # strategy so paper and live evaluate identical signals. Set to
    # "capital_preservation_v1" to run the low-frequency mean-reversion strategy live.
    live_strategy: str = "momentum_breakout_v1"
    # Go-live gate: require the live strategy to have PASSED a recent walk-forward
    # validation (on the live timeframe) before it may open new trades. Blocks new
    # entries (open positions are still managed) until a passing, fresh run exists.
    # Disable only if you validate strategies out-of-band.
    live_require_walkforward: bool = True
    # Max age (days) of the passing walk-forward run before it is considered stale.
    # 45 days for a 5m/15m momentum strategy: crypto spans multiple regime shifts
    # in 90 days, so a 90-day-stale validation providing go-live cover is too
    # generous. Re-validate roughly monthly.
    live_validation_max_age_days: int = 45
    # Live market. "spot" (proven path; long-only — short signals are skipped) or
    # "futures" (USDT-perpetual; enables shorts + leverage to fully mirror paper).
    # Default SPOT for safety: validate futures keys on Gate.io testnet before
    # switching, since live futures order routing cannot be exercised in CI.
    trading_market: str = "spot"
    futures_settle: str = "usdt"
    futures_leverage: int = 5
    # Liquidation-distance guard (futures only). Each cycle the live futures
    # position is read back and the distance from the mark price to the
    # exchange's liquidation price is computed. When distance falls below this
    # fraction the position is force-closed BEFORE the exchange's liquidation
    # engine fires — defending against a fast adverse move that gaps through
    # the (15-min-polled) ATR stop. Set to 0 to disable.
    futures_liq_warning_pct: float = 0.03
    # Verify the configured leverage was actually applied before placing a
    # futures entry (read back the contract leverage and abort on mismatch).
    futures_leverage_verify: bool = True
    default_quote_currency: str = "USDT"
    # Stablecoins counted as cash at par (not marked to market) in equity.
    stablecoins: str = "USDT,USDC,DAI,TUSD,FDUSD"

    # Opportunity cost of idle capital: the ~risk-free yield idle USDT could earn
    # (e.g. exchange lending/Earn). The strategy must beat this hurdle to add value.
    annual_risk_free_rate: float = 0.04

    # Graded de-risking: shrink size as account drawdown approaches the max.
    drawdown_derisk_enabled: bool = True
    # Floor for the drawdown de-risk multiplier. 0.0 means new entries are sized
    # to ZERO near the max drawdown — which halts recovery (no new trades can
    # dig out). 0.2 keeps a 20%-sized entry alive near the limit so recovery is
    # still possible while risk is heavily reduced.
    drawdown_derisk_floor: float = 0.2

    # --- Stablecoin (quote) depeg monitoring ---
    # Pair used to proxy the quote stablecoin's peg (drift from 1.0).
    quote_depeg_reference_pair: str = "USDC_USDT"
    quote_depeg_threshold_pct: float = 0.01  # 1% drift from parity
    quote_depeg_halt: bool = True            # pause new entries while depegged

    # Risk-based position sizing (opt-in): size each trade so the loss-to-stop
    # equals max_risk_per_trade_pct of equity (true fixed-fractional risk), instead
    # of allocating a fixed notional. Never exceeds max_capital_per_trade_pct notional.
    risk_based_sizing_enabled: bool = True

    # Correlation-aware entry filter (opt-in): skip a new entry whose returns are
    # too correlated with an already-open position, so "8 positions" don't collapse
    # into one concentrated directional bet.
    correlation_filter_enabled: bool = True
    # Pairwise correlation cap (candidate vs EACH open position). Lowered from
    # 0.85 (which let 8 positions at 0.84 corr each pass — effectively one 8x
    # directional bet) to 0.65 so a "diversified" book is actually diversified.
    max_position_correlation: float = 0.65
    # Aggregate portfolio correlation cap: the MEAN pairwise correlation of the
    # candidate + all open positions must stay below this. Three positions each
    # at 0.64 pairwise corr pass the pairwise cap but form one concentrated
    # bet — the aggregate cap catches that. 0 disables (legacy pairwise-only).
    max_portfolio_correlation: float = 0.55

    # --- Volatility targeting (opt-in): scale size inversely to volatility ---
    vol_targeting_enabled: bool = False
    vol_target_atr_pct: float = 0.02          # target ATR as a fraction of price
    vol_target_min_multiplier: float = 0.25
    vol_target_max_multiplier: float = 1.5

    # --- Live strategy entry thresholds (tunable per market) ---
    strategy_rsi_threshold: float = 35.0
    strategy_rsi_overbought: float = 65.0
    # EMA200 trend filter: when enabled, only enter long while price is above the
    # 200-period EMA (capital preservation — avoid buying in confirmed downtrends).
    strategy_trend_filter_enabled: bool = True
    # Trend tolerance for LONG entries: allow a long when price is within this
    # fraction BELOW EMA200 (0.0 = strict "must be above EMA200", live default).
    # Paper overrides this (see paper_trend_tolerance_pct) so mild pullbacks below a
    # laggy 400-bar EMA200 still produce observable activity. Live stays strict.
    strategy_trend_tolerance_pct: float = 0.0
    # Number of candles fetched per scan. EMA200 needs >=200 and only converges
    # well with extra history, so fetch a generous window (bounded by max_query_limit).
    candle_history_limit: int = 400
    strategy_ema20_distance_pct: float = 0.015
    # Max 24h range as a fraction of price before an entry is rejected. 0.12
    # allows normal crypto volatility while still filtering extreme moves.
    strategy_max_24h_range_pct: float = 0.12

    # --- Paper-trading position sizing (ATR/risk-based, leverage-aware) ---
    # Size each paper trade so the loss-to-stop equals this fraction of equity
    # (true fixed-fractional risk), scaled by ATR, capped at a leverage notional
    # limit. 0.5% risk/trade is the frequent-trading default (many small bets).
    paper_position_risk_pct: float = 0.005
    paper_atr_stop_multiplier: float = 2.0
    # Reward:risk for the fixed take-profit (trailing handles the rest of the run).
    paper_tp_rr: float = 1.5
    paper_max_capital_per_trade_pct: float = 0.10
    # Fallback notional fraction when ATR is unavailable (conservative).
    paper_fallback_capital_pct: float = 0.02

    # --- Futures simulation: leverage + fees ---
    # Notional per trade may reach paper_leverage * equity (margin trading). The
    # per-trade RISK is still bounded by paper_position_risk_pct above; leverage only
    # raises the notional CEILING so small-stop breakouts can take a meaningful size.
    paper_leverage: float = 5.0
    # Gate.io futures taker/maker fees. Taker 5 bps, maker 2 bps.
    paper_taker_fee: float = 0.0005
    paper_maker_fee: float = 0.0002
    # Gate.io SPOT taker/maker fees, used when paper mirrors a SPOT live account.
    # Set these to YOUR Gate.io spot fee tier (base tier is ~0.2%; ~0.1% with a GT
    # deduction) so paper drag matches what you actually pay live.
    paper_spot_taker_fee: float = 0.001
    paper_spot_maker_fee: float = 0.001
    # Mirror live: when true (default), paper adopts the LIVE account's economics —
    # same timeframe (market_data_interval), market/direction/leverage (spot=>1x,
    # long-only; futures=>futures_leverage, long+short), spot-vs-futures fees,
    # funding, and live risk sizing (max_risk_per_trade_pct + StrategySettings
    # atr_multiplier / min_reward_risk / max_capital_per_trade_pct, live loss/
    # drawdown limits). Turn OFF to run paper standalone on its own paper_* knobs.
    paper_mirror_live: bool = True
    # Auto-pause thresholds (applied to new paper accounts and migrated onto an
    # existing account still on the legacy spot limits). Widened for 5x leverage:
    # mark-to-market equity swings ~leverage x the market, so the spot-era 5%/25%
    # limits tripped on ordinary intraday volatility.
    paper_max_daily_loss_pct: float = 0.08
    paper_max_drawdown_pct: float = 0.30
    # Kelly position scaling needs a track record; off by default so cold-start sizing
    # is deterministic (pure fixed-fractional risk).
    paper_kelly_enabled: bool = False
    # Legacy fixed-pct dynamic stop (tightens to a flat % of price before breakeven).
    # OFF by default: it silently overrides the ATR stop the position was sized to,
    # mis-stating realised risk. ATR stop + trailing govern exits instead.
    paper_dynamic_pct_stop_enabled: bool = False

    # --- Momentum / breakout strategy (momentum_breakout_v1) ---
    # Active paper strategy. "momentum_breakout_v1" (frequent, long+short) or
    # "capital_preservation_v1" (low-frequency mean-reversion).
    paper_strategy: str = "momentum_breakout_v1"
    momentum_ema_fast: int = 9
    momentum_ema_slow: int = 21
    momentum_ema_trend: int = 50
    momentum_donchian_lookback: int = 20
    momentum_vol_spike_mult: float = 1.3
    momentum_rsi_long_max: float = 80.0
    momentum_rsi_short_min: float = 20.0
    # Minimum ATR as a fraction of price; below this the move can't clear costs.
    # Bumped from 0.0015 (0.15%) to 0.004 (0.4%) — the old floor was BELOW the
    # typical round-trip cost (2x taker ~0.1% + spread + slippage), so a
    # "breakout" could fire inside the bid-ask and be instantly underwater.
    momentum_min_atr_pct: float = 0.004
    # Breakout must clear the prior extreme by this fraction of ATR (noise filter).
    # Treated as a FLOOR: the effective buffer is max(this * ATR, round_trip_cost)
    # so a breakout can never fire inside the realistic fee+spread+slippage band.
    momentum_breakout_buffer_atr: float = 0.05
    # Estimated round-trip cost (taker in + taker out + spread + slippage) as a
    # fraction of price. The breakout buffer is floored at this so a "breakout"
    # smaller than the cost of round-tripping never fires. Futures taker 5bps x2
    # + spread 2bps + slippage 5bps ≈ 0.0022; spot base tier ~0.2% x2 + ... ≈ 0.005.
    # Default futures; override via env for spot.
    momentum_round_trip_cost_pct: float = 0.0022
    momentum_allow_short: bool = True

    # --- Financing / funding carry on held positions ---
    # Perpetual funding / spot borrow drag, modeled as a conservative daily cost
    # on notional over the holding period so simulated PnL is not overstated.
    # ~0.01% per 8h funding ≈ 0.03%/day is a typical neutral-market baseline.
    funding_cost_enabled: bool = True
    funding_daily_rate_pct: float = 0.0003
    # --- Funding rate as a SIGNAL input (futures only) ---
    # The perpetual funding rate is a microstructure signal: a strongly positive
    # funding rate means longs pay shorts — a headwind for new longs and a
    # tailwind for new shorts. A strongly negative rate is the mirror. Extreme
    # funding signals crowded positioning (contrarian). The momentum strategy
    # uses this to de-risk entries that would carry an adverse funding drag.
    # Thresholds are FRACTIONS (0.0005 = 0.05% per 8h funding interval).
    # When |funding| > funding_signal_threshold, the entry risk multiplier is
    # scaled by funding_signal_risk_mult (0.5 = halve size) in the adverse
    # direction; a favorable funding does NOT boost size (asymmetric — protect
    # capital first). 0 disables the funding signal.
    funding_signal_enabled: bool = True
    funding_signal_threshold_pct: float = 0.0005
    funding_signal_risk_mult: float = 0.5

    # --- Paper-trading entry threshold overrides ---
    # Paper runs DELIBERATELY looser than live so the simulation generates enough
    # activity to observe (live's strict capital-preservation thresholds rarely
    # fire: an uptrend with RSI<35 within 1.5% of EMA20 is a rare confluence).
    # RSI<45 catches ordinary pullbacks; a 3% EMA20 band widens the entry zone.
    # Set these equal to the live strategy_* values to make paper mirror live.
    # Override via env PAPER_RSI_THRESHOLD, PAPER_EMA20_DISTANCE_PCT, PAPER_TREND_FILTER_ENABLED.
    paper_rsi_threshold: float = 45.0
    paper_ema20_distance_pct: float = 0.03
    paper_trend_filter_enabled: bool = True
    # Paper LONG trend tolerance: enter longs when price is within 2% below the
    # 400-bar EMA200. In neutral/mildly-down chop the laggy EMA200 sits just above
    # price and reads as "downtrend", blocking all longs; a small band keeps the
    # simulation active on healthy pullbacks. Override via PAPER_TREND_TOLERANCE_PCT.
    paper_trend_tolerance_pct: float = 0.02
    # Default trailing-stop distance (used when StrategySettings is missing).
    strategy_trailing_stop_pct: float = 0.03
    # ATR Chandelier trailing stop: when enabled, the trailing stop distance is
    # ATR * chandelier_mult instead of a fixed % of price. Volatility-adaptive:
    # in calm markets the stop rides tight (capture profit), in volatile markets
    # it gives room (avoid whipsaw). The fixed-% trailing is the fallback when
    # disabled or ATR is unavailable. The Chandelier exit (Le Beau) is the
    # standard trend-following trailing — it lets winners run in trends and
    # tightens in chop, where a fixed % either whipsaws or lags.
    chandelier_trailing_enabled: bool = True
    chandelier_atr_mult: float = 3.0
    # Number of candles that represent a "daily" range (depends on candle interval).
    strategy_daily_range_candles: int = 24
    # Tradable universe (comma-separated Gate.io spot pairs). Expanded to a broader
    # set of liquid USDT pairs; override via TRADING_SYMBOLS to add/remove coins.
    trading_symbols: str = (
        "BTC_USDT,ETH_USDT,BNB_USDT,XRP_USDT,SOL_USDT,DOGE_USDT,ADA_USDT,TRX_USDT,"
        "LINK_USDT,AVAX_USDT,DOT_USDT,LTC_USDT,BCH_USDT,ATOM_USDT,UNI_USDT,XLM_USDT,"
        "NEAR_USDT,APT_USDT,ARB_USDT,OP_USDT,FIL_USDT,INJ_USDT,"
        "SUI_USDT,SEI_USDT,TIA_USDT,PENDLE_USDT,WLD_USDT,FET_USDT,RENDER_USDT,"
        "STX_USDT,IMX_USDT,MANTA_USDT,JUP_USDT,PYTH_USDT,WIF_USDT,BONK_USDT,"
        "PEPE_USDT,FLOKI_USDT,MEME_USDT,ORDI_USDT,SATS_USDT"
    )
    # Minimum volume ratio: reject entries when current volume is below this fraction
    # of the recent average volume (e.g., 0.3 = 30% of average).
    strategy_min_volume_ratio: float = 0.3
    # Maximum absolute dollar loss per trade as a fraction of equity. This provides
    # a hard cap on any single trade's risk, protecting against flash crashes where
    # the stop-loss distance is wide but the trade size is large.
    max_risk_per_trade_pct: float = 0.02
    # Maximum total portfolio exposure as a fraction of equity. Prevents over-allocation
    # when max_open_positions is set too high. This is the GROSS notional cap
    # (sum of |entry_price * quantity| across open positions, longs + shorts both
    # add) — bounds total market exposure regardless of direction.
    max_total_exposure_pct: float = 0.30
    # Maximum NET portfolio exposure as a fraction of equity (longs minus
    # shorts, signed). A long and a short on the same asset partially offset, so
    # the gross cap can over-bind a market-neutral book while leaving a one-way
    # 30%-long book unchecked on the net side. The net cap bounds the
    # directional bias: 0.30 == up to 30% net long (or short). 0 disables
    # (legacy gross-only).
    max_net_exposure_pct: float = 0.30
    # Fractional Kelly position sizing (opt-in). When enabled and a track record
    # exists, size is scaled by ¼-Kelly (Kelly fraction / 4) — edge-quality-aware
    # sizing that grows with a demonstrated win-rate/payoff edge and shrinks
    # under noise. ¼ (not full) Kelly cuts the variance and drawdown of full
    # Kelly at ~94% of the growth rate — the standard practical choice. Capped to
    # [0.25, 1.0] so it never zeros out a cold-start or a thin edge. Off by
    # default: cold-start sizing stays deterministic (pure fixed-fractional risk).
    kelly_sizing_enabled: bool = False
    kelly_fraction: float = 0.25  # 0.25 = quarter-Kelly
    # Minimum trades before Kelly is applied (need a track record to estimate edge).
    kelly_min_trades: int = 30

    # Equity used when the exchange balance cannot be fetched (no keys / offline).
    fallback_equity: float = 10000.0
    # Max account drawdown from peak equity before the circuit breaker trips.
    max_account_drawdown_pct: float = 0.15
    # Max age (seconds) of an equity snapshot before it is considered stale and
    # unsafe to size new positions against. Trading runs every 15m, so allow ~2 cycles.
    max_equity_staleness_seconds: int = 1800

    # --- Live worker watchdog / heartbeat ---
    # The live scheduler writes a heartbeat every cycle; the API process polls it
    # and alerts (Telegram + log) when the worker goes silent — so a crashed or
    # stuck worker that would leave open positions unmanaged is surfaced.
    # ON by default: the watchdog primes silently on first observation and only
    # alerts on a healthy->stale TRANSITION, so a paper-only deployment (no
    # scheduler, no heartbeat) does NOT get spammed — it simply never sees a
    # transition. Set WORKER_WATCHDOG_ENABLED=false only if you explicitly want
    # no monitoring at all.
    worker_watchdog_enabled: bool = True
    # How often the API watchdog checks the heartbeat (seconds).
    worker_watchdog_check_seconds: int = 300
    # Heartbeat older than this is treated as a dead/stuck worker. The trading
    # loop runs every 15m, so ~3 missed cycles (45m) avoids false alarms.
    worker_heartbeat_stale_seconds: int = 2700
    gateio_ws_url: str = "wss://api.gateio.ws/ws/v4/"
    market_data_interval: str = "15m"
    # Paper trading runs on a faster timeframe than live (frequent momentum/breakout
    # strategy). Falls back to market_data_interval when unset.
    paper_market_data_interval: str = "5m"
    # How often the paper-trading engine re-evaluates entries on real candles.
    # 15s on 5m candles ensures a fresh bar is picked up within a fraction of a bar.
    paper_eval_interval_seconds: int = 15
    # Paper order type: "market" (default) or "limit" (maker, lower fees)
    paper_order_type: str = "market"
    # Multi-timeframe confirmation: when enabled, entries require the higher
    # timeframe (4h) trend to align with the entry direction.
    strategy_mtf_enabled: bool = True
    strategy_mtf_interval: str = "4h"

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
    # WF method: "anchored" (expanding window) or "rolling" (equal-sized chunks).
    research_wf_method: str = "anchored"
    # Population size per research-loop generation.
    research_population: int = 12
    research_survivors: int = 4
    # Cross-validation folds for overfit detection (k-fold purged CV).
    research_cv_folds: int = 5
    # Purge gap (bars) dropped between IS and OOS folds in k-fold CV — the
    # López de Prado leakage-prevention technique. ~ the longest indicator
    # lookback (e.g. 200 for EMA200) so a position held across the boundary
    # does not leak IS alpha into the OOS fold. 0 = no purge (legacy behavior,
    # understates overfit).
    research_cv_purge_bars: int = 200
    # Minimum track record in calendar days required for promotion.
    research_min_track_days: int = 90
    # Deflated Sharpe Ratio confidence threshold (p-value, 0..1).
    research_dsr_confidence: float = 0.95

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
    # Pre-trade slippage guard: skip a market BUY when the live price has already
    # moved adversely beyond this fraction of the signal price (don't chase fills).
    # Set to 0 to disable.
    entry_max_slippage_pct: float = 0.01
    # Entry order type: "market" (taker, always fills, pays slippage), "limit"
    # (maker, posts at signal price, may miss), or "adaptive" (try a passive limit
    # first with a short timeout, fall back to market on timeout — captures the
    # maker rebate when possible without sacrificing fill rate).
    entry_order_type: str = "adaptive"
    # For adaptive/limit entries: how long to wait for a maker fill (seconds)
    # before falling back to a market order. Short enough to not stall the cycle.
    entry_limit_timeout_seconds: int = 30
    # Limit offset: post the passive limit this fraction BELOW the signal close
    # (long) / ABOVE (short) so it rests as a maker order. 0 = at the signal price.
    entry_limit_offset_pct: float = 0.0
    # Order splitting: when the entry notional exceeds this fraction of equity,
    # split into N TWAP child orders to reduce market impact on less-liquid
    # altcoins (WIF/BONK/PEPE etc). 0 disables splitting.
    entry_split_threshold_pct: float = 0.03
    entry_split_child_count: int = 3
    # TCA feedback: when the recent fill slippage exceeds this fraction, switch
    # the NEXT entry to a passive limit order (capture the maker rebate instead
    # of paying taker slippage). 0 disables the TCA feedback loop.
    tca_slippage_feedback_pct: float = 0.003

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

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+psycopg://", 1)
        if v.startswith("postgresql://") and not v.startswith("postgresql+psycopg://"):
            return v.replace("postgresql://", "postgresql+psycopg://", 1)
        return v

    @property
    def symbols(self) -> list[str]:
        # Normalize (uppercase), drop blanks and de-duplicate while preserving the
        # configured order, so a large/edited universe stays clean and stable.
        seen: set[str] = set()
        out: list[str] = []
        for symbol in self.trading_symbols.split(","):
            sym = symbol.strip().upper()
            if sym and sym not in seen:
                seen.add(sym)
                out.append(sym)
        return out

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
        """Validate secrets/CORS. In production a misconfiguration is fatal and
        raises RuntimeError (fail fast); in non-production the same problems are
        returned as warnings so local dev still runs."""
        warnings: list[str] = []
        weak_secret = self.secret_key in ("", "change-me")
        if weak_secret:
            if self.is_production:
                warnings.append(
                    "SECRET_KEY is the insecure default ('change-me') — "
                    "set a strong random value for production."
                )
            else:
                warnings.append("SECRET_KEY is the insecure default ('change-me').")
        if not self.fernet_key:
            if self.is_production:
                warnings.append(
                    "FERNET_KEY is unset — stored API secrets are not encrypted. "
                    "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
                )
            else:
                warnings.append("FERNET_KEY is unset; stored API secrets are not encrypted.")
        if self.is_production:
            for origin in self.cors_origin_list:
                if "localhost" in origin or "127.0.0.1" in origin:
                    warnings.append(
                        f"CORS origin '{origin}' includes localhost — "
                        f"requests from the browser will be blocked. "
                        f"Set CORS_ORIGINS to your production domain."
                    )
        if self.is_production and warnings:
            raise RuntimeError("Insecure production configuration: " + "; ".join(warnings))
        return warnings


@lru_cache
def get_settings() -> Settings:
    return Settings()
