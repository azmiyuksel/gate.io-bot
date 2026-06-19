from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.repositories.trading import (
    AccountSnapshotRepository,
    PositionRepository,
    StrategySettingsRepository,
    TradeRepository,
    day_start_utc,
    week_start_utc,
)


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str
    quantity: Decimal = Decimal("0")
    stop_loss: Decimal = Decimal("0")
    take_profit: Decimal = Decimal("0")


def drawdown_risk_multiplier(
    drawdown: Decimal, max_drawdown: Decimal, floor: Decimal = Decimal("0")
) -> Decimal:
    """Graded de-risking: shrink position size as account drawdown deepens.

    Returns 1.0 at no drawdown and falls linearly toward `floor` as drawdown
    approaches `max_drawdown` (where the circuit breaker hard-stops). This
    respects recovery math — deeper drawdowns need disproportionately larger
    gains to recover, so risk is cut before the hard limit."""
    if max_drawdown <= 0:
        raise ValueError("max_drawdown must be positive")
    if drawdown <= 0:
        return Decimal("1")
    mult = Decimal("1") - (drawdown / max_drawdown)
    return max(floor, min(mult, Decimal("1")))


def vol_target_multiplier(
    atr_pct: Decimal, target_pct: Decimal, min_mult: Decimal, max_mult: Decimal
) -> Decimal:
    """Volatility-targeting size multiplier: scale inversely to volatility so
    per-trade risk is steadier across calm/volatile markets.

    atr_pct is ATR as a fraction of price; when it exceeds the target, size is
    reduced; when below, size is increased (within [min_mult, max_mult])."""
    if atr_pct <= 0:
        return Decimal("1")
    raw = target_pct / atr_pct
    return max(min_mult, min(raw, max_mult))


class RiskManager:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.positions = PositionRepository(db)
        self.trades = TradeRepository(db)
        self.settings = StrategySettingsRepository(db)
        self.snapshots = AccountSnapshotRepository(db)

    def _period_pnl(self, current_equity: Decimal, since) -> Decimal:
        """Mark-to-market PnL for the period: current equity minus equity carried
        into the period (includes UNREALIZED PnL of open positions, since
        `current_equity` is marked to market). Falls back to realized-only PnL
        when no equity snapshots exist. This stops an open position from blowing
        through the loss limit while reporting zero realized loss."""
        start_equity = self.snapshots.equity_at_period_start(since)
        if start_equity is not None and start_equity > 0:
            return current_equity - start_equity
        return self.trades.pnl_since(since)

    def approve_entry(
        self,
        equity: Decimal,
        entry: Decimal,
        atr_value: Decimal,
        side: str = "long",
        expectancy_type: str = "reversion",
        symbol: str = "",
        strategy_name: str = "",
    ) -> RiskDecision:
        # Master env kill-switch: live entries require BOT_ENABLED=true as well
        # as the strategy's own enable flag (defense-in-depth alongside scheduler).
        if not get_settings().bot_enabled:
            return RiskDecision(False, "bot_disabled")
        if entry <= 0 or atr_value <= 0:
            return RiskDecision(False, "invalid_price_data")
        # Defense-in-depth: never open a new position while the circuit breaker is
        # tripped, even if some other path failed to halt the strategy.
        from app.services.risk.circuit_breaker import CircuitBreaker

        if CircuitBreaker(self.db).is_tripped():
            return RiskDecision(False, "circuit_breaker_tripped")
        # Lock the (single-row) StrategySettings for the duration of the
        # transaction so concurrent approvals serialize: the check below and the
        # caller's subsequent position insert cannot interleave and both pass the
        # max_open_positions / exposure guards (no-op on SQLite).
        settings = self.settings.current_for_update()
        if not settings.is_enabled:
            return RiskDecision(False, "strategy_disabled")
        if self.positions.open_count() >= settings.max_open_positions:
            return RiskDecision(False, "max_open_positions")

        # --- TOTAL EXPOSURE GUARD (gross) ---
        # Sum existing open position values plus the proposed new notional and
        # ensure the total stays below a safe fraction of equity. Gross = longs
        # + shorts both add (bounds total market exposure regardless of direction).
        max_total_exposure_pct = Decimal(str(get_settings().max_total_exposure_pct))
        existing_exposure = self.positions.open_notional()
        new_notional = equity * settings.max_capital_per_trade_pct
        if existing_exposure + new_notional > equity * max_total_exposure_pct:
            return RiskDecision(
                False,
                f"max_total_exposure: {existing_exposure + new_notional:.2f} > limit {equity * max_total_exposure_pct:.2f}",
            )

        # --- NET EXPOSURE GUARD (directional bias) ---
        # Longs minus shorts (signed). A market-neutral book (longs ≈ shorts)
        # has near-zero net and should not be over-bound by the gross cap, while
        # a one-way long book hits the net cap. Binds the directional bias so
        # "8 longs" can't become a 30%+ one-way bet. The new position's signed
        # notional is added to the existing net to check the post-trade bias.
        max_net_exposure_pct = Decimal(str(get_settings().max_net_exposure_pct))
        if max_net_exposure_pct > 0:
            existing_net = self.positions.net_notional()
            signed_new = new_notional if side != "short" else -new_notional
            post_net = existing_net + signed_new
            if abs(post_net) > equity * max_net_exposure_pct:
                return RiskDecision(
                    False,
                    f"max_net_exposure: post-trade net {post_net:.2f} "
                    f"|abs| > limit {equity * max_net_exposure_pct:.2f}",
                )

        # --- BETA-WEIGHTED NET EXPOSURE GUARD (market-factor risk) ---
        # Like the net guard but each position's notional is weighted by its
        # beta to BTC (the crypto market factor). A 30%-net-long book in
        # high-beta alts (SOL beta ~1.5) is more directional than 30% in BTC —
        # the beta-weighted cap catches that. Beta is estimated from the
        # correlation engine's covariance; missing symbols default to beta 1.0
        # (conservative — assume market beta when unknown).
        max_beta_pct = Decimal(str(getattr(get_settings(), "max_beta_weighted_exposure_pct", 0) or 0))
        if max_beta_pct > 0:
            betas = self._betas_to_benchmark()
            existing_beta_net = self.positions.beta_weighted_net_notional(
                betas, benchmark=get_settings().beta_benchmark_symbol
            )
            beta_new = betas.get(symbol, 1.0)
            signed_beta_new = (new_notional if side != "short" else -new_notional) * Decimal(str(beta_new))
            post_beta_net = existing_beta_net + signed_beta_new
            if abs(post_beta_net) > equity * max_beta_pct:
                return RiskDecision(
                    False,
                    f"max_beta_weighted_exposure: post-trade beta-net {post_beta_net:.2f} "
                    f"|abs| > limit {equity * max_beta_pct:.2f}",
                )

        daily_limit = -(equity * settings.daily_max_loss_pct)
        weekly_limit = -(equity * settings.weekly_max_loss_pct)
        if self._period_pnl(equity, day_start_utc()) <= daily_limit:
            return RiskDecision(False, "daily_loss_limit")
        if self._period_pnl(equity, week_start_utc()) <= weekly_limit:
            return RiskDecision(False, "weekly_loss_limit")

        # Risk levels first — sizing may depend on the stop distance. The stop is
        # on the LOSS side of entry and the target on the PROFIT side, mirrored by
        # direction, so shorts get a valid protective stop ABOVE entry (a long-only
        # formula would put a short's stop below entry where it can never trigger).
        stop_distance = atr_value * settings.atr_multiplier
        is_long = side != "short"
        # Take-profit is set only for mean-reversion strategies. A trend-following
        # (momentum/breakout) strategy edges on the fat right tail — a fixed R:R
        # take-profit cuts the big winners that are its main edge, so the TP is
        # left at 0 (disabled) and winners are managed by trailing + breakeven.
        use_take_profit = expectancy_type != "trend"
        if is_long:
            stop_loss = entry - stop_distance
            take_profit = entry + (stop_distance * settings.min_reward_risk) if use_take_profit else Decimal("0")
            valid = stop_loss > 0 and (not use_take_profit or take_profit > entry)
        else:
            stop_loss = entry + stop_distance
            take_profit = entry - (stop_distance * settings.min_reward_risk) if use_take_profit else Decimal("0")
            valid = (not use_take_profit or take_profit > 0) and stop_loss > entry
        risk_per_unit = stop_distance
        if not valid or risk_per_unit <= 0:
            return RiskDecision(False, "invalid_risk_levels")

        app_settings = get_settings()
        notional_cap = equity * settings.max_capital_per_trade_pct
        if app_settings.risk_based_sizing_enabled:
            # Fixed-fractional RISK sizing: size so the loss if stopped out equals
            # max_risk_per_trade_pct of equity. Cap at the notional limit so the
            # total-exposure guard above stays valid.
            risk_budget = equity * Decimal(str(app_settings.max_risk_per_trade_pct))
            quantity = risk_budget / risk_per_unit
            if quantity * entry > notional_cap:
                quantity = notional_cap / entry
        else:
            # Notional-based: allocate `max_capital_per_trade_pct` of equity. The
            # loss if stopped out is ≈ notional * stop_distance/entry, i.e. smaller
            # than the allocated notional.
            quantity = notional_cap / entry

        # Optional volatility targeting: feed the current volatility (ATR) back
        # into sizing so per-trade risk is steadier across calm/volatile markets.
        if app_settings.vol_targeting_enabled and entry > 0 and atr_value > 0:
            mult = vol_target_multiplier(
                atr_value / entry,
                Decimal(str(app_settings.vol_target_atr_pct)),
                Decimal(str(app_settings.vol_target_min_multiplier)),
                Decimal(str(app_settings.vol_target_max_multiplier)),
            )
            quantity = quantity * mult

        # Optional fractional Kelly sizing: scale by edge quality once a track
        # record exists. ¼-Kelly grows size with a demonstrated win-rate/payoff
        # edge and shrinks under noise, capped to [0.25, 1.0] so it never zeros
        # out a cold-start or a thin edge. Off by default (deterministic sizing).
        if getattr(app_settings, "kelly_sizing_enabled", False):
            kelly_scale = self._kelly_scale(side, strategy_name=strategy_name)
            if kelly_scale is not None and kelly_scale != Decimal("1"):
                quantity = quantity * kelly_scale

        # --- POST-SCALING GROSS EXPOSURE CLAMP ---
        # The gross/net exposure guards above were checked against the
        # PRE-scaling notional (equity * max_capital_per_trade_pct). Volatility
        # targeting can scale the quantity UP (vol_target_max_multiplier > 1, e.g.
        # 1.5x in calm markets), so the actual notional can breach the gross
        # exposure cap that was validated. Re-clamp the scaled notional to the
        # remaining gross-exposure headroom so the cap holds after scaling.
        exposure_headroom = equity * max_total_exposure_pct - existing_exposure
        if exposure_headroom > 0 and quantity * entry > exposure_headroom:
            quantity = exposure_headroom / entry

        # --- PER-TRADE MAXIMUM DOLLAR LOSS GUARD ---
        # Run AFTER all scaling adjustments (vol target, Kelly) so the final
        # quantity is clamped, not the pre-adjustment estimate.  Previous
        # placement before scaling let multiplied quantities exceed the risk cap.
        max_loss_per_trade_pct = Decimal(str(get_settings().max_risk_per_trade_pct))
        max_loss_dollar = equity * max_loss_per_trade_pct
        max_loss_from_trade = risk_per_unit * quantity
        if max_loss_from_trade > max_loss_dollar:
            quantity = max_loss_dollar / risk_per_unit if risk_per_unit > 0 else quantity

        return RiskDecision(True, "approved", quantity, stop_loss, take_profit)

    def _betas_to_benchmark(self) -> dict[str, float]:
        """Beta of each open position's symbol to the benchmark (default BTC).

        Beta = Cov(symbol, benchmark) / Var(benchmark), estimated from the
        correlation engine's covariance matrix over the trading timeframe.
        Missing symbols default to 1.0 (conservative — assume market beta).
        Returns {symbol: beta} for the benchmark + all open position symbols.
        """
        try:
            from app.portfolio.correlation import CorrelationEngine

            bench = get_settings().beta_benchmark_symbol
            symbols = list({bench, *self.positions.open_symbols()})
            if len(symbols) < 2:
                return {bench: 1.0}
            corr = CorrelationEngine(self.db).calculate_correlation(
                symbols, get_settings().market_data_interval
            )
            cov = corr.get("covariance", {})
            bench_var = float(cov.get(bench, {}).get(bench, 0.0) or 0.0)
            if bench_var <= 0:
                return {s: 1.0 for s in symbols}
            return {
                s: float(cov.get(s, {}).get(bench, 0.0) or 0.0) / bench_var
                for s in symbols
            }
        except Exception:
            # Best-effort: on any failure, default all to 1.0 (raw notional
            # equivalent — the beta guard degrades to the plain net guard).
            return {}

    def _kelly_scale(self, side: str, strategy_name: str = "") -> Decimal | None:
        """Fractional Kelly scaling factor for the current strategy track record.

        Computes the Kelly fraction f* = W - (1-W)/R from the realized win-rate
        W and average win/loss ratio R, then scales by `kelly_fraction` (1/4 by
        default — full Kelly has too much variance/drawdown for live capital).
        Capped to [0.25, 1.0]: a cold-start or thin edge never zeros out sizing
        (floor 0.25), and a strong edge never more than doubles it (cap 1.0).

        Returns None when there is no track record yet (kelly_min_trades not
        met) — the caller keeps the deterministic fixed-fractional size.
        """
        settings = get_settings()
        min_trades = int(getattr(settings, "kelly_min_trades", 30) or 30)
        from app.repositories.trading import TradeRepository

        trades = TradeRepository(self.db).all_recent(limit=500)
        # Filter by strategy so edge estimate is not diluted by other strategies'
        # performance.  A momentum strategy's sizing should not be reduced by a
        # reversion strategy's losses.
        if strategy_name:
            trades = [t for t in trades if getattr(t, "strategy_name", None) == strategy_name]
        # Filter to the side being sized (long/short edges can differ).
        target_side = "buy" if side != "short" else "sell"
        side_trades = []
        for t in trades:
            # t.side may be an OrderSide enum or a raw string depending on the
            # driver (SQLite returns strings); normalize both.
            t_side = t.side.value if hasattr(t.side, "value") else str(t.side)
            if t_side == target_side:
                side_trades.append(t)
        if len(side_trades) < min_trades:
            return None
        wins = [float(t.realized_pnl) for t in side_trades if float(t.realized_pnl) > 0]
        losses = [float(t.realized_pnl) for t in side_trades if float(t.realized_pnl) < 0]
        if not wins or not losses:
            return None
        win_rate = len(wins) / len(side_trades)
        avg_win = sum(wins) / len(wins)
        avg_loss = abs(sum(losses) / len(losses))
        if avg_loss <= 0:
            return None
        payoff_ratio = avg_win / avg_loss  # R
        kelly_f = win_rate - (1 - win_rate) / max(payoff_ratio, 0.01)
        if kelly_f < 0:
            # NEGATIVE edge (demonstrated losing track record): de-risk harder
            # than the no-edge floor. We don't go to zero so the strategy can
            # still sample a few trades and recover its estimate, but a proven
            # loser should not keep trading at the same size as a flat one. The
            # fixed-fractional risk budget still bounds the per-trade loss.
            return Decimal("0.1")
        if kelly_f == 0:
            # No demonstrated edge (flat) — keep the floor (0.25) so sizing is
            # not zeroed out; the fixed-fractional risk budget still bounds loss.
            return Decimal("0.25")
        fraction = Decimal(str(getattr(settings, "kelly_fraction", 0.25) or 0.25))
        scale = Decimal(str(kelly_f)) * fraction
        # Clamp to [0.25, 1.0].
        if scale < Decimal("0.25"):
            return Decimal("0.25")
        if scale > Decimal("1.0"):
            return Decimal("1.0")
        return scale
