"""Effective paper-trading execution parameters.

Single source of truth that resolves what economics the paper engine should
simulate. When ``paper_mirror_live`` is on (default), paper adopts the LIVE
account's settings so simulation results track real trading — no surprises when
switching to real money. When off, paper uses its own ``paper_*`` knobs.

Live parity covered here: timeframe, market/direction/leverage, spot-vs-futures
fees, funding, fixed-fractional risk sizing, the per-trade notional cap, and the
loss/drawdown/exposure auto-pause limits. Residual differences that a simulator
cannot reproduce (live regime/health/data-quality/correlation/slippage filters
and real exchange fills) make LIVE somewhat more conservative than paper.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.repositories.trading import StrategySettingsRepository


@dataclass(frozen=True)
class PaperExec:
    mirror: bool
    market: str                # "spot" | "futures"
    interval: str
    leverage: Decimal
    taker_fee: Decimal
    maker_fee: Decimal
    funding_enabled: bool
    allow_short: bool
    risk_pct: Decimal          # fixed-fractional risk per trade
    atr_stop_multiplier: Decimal
    tp_rr: Decimal             # take-profit reward:risk
    notional_cap_pct: Decimal  # max notional per trade as a fraction of equity
    # Auto-pause / risk limits
    daily_max_loss_pct: Decimal
    max_drawdown_pct: Decimal
    max_open_positions: int
    max_exposure_pct: Decimal


def resolve_paper_exec(db: Session, settings) -> PaperExec:
    """Resolve effective paper params from settings (+ live StrategySettings)."""
    if not settings.paper_mirror_live:
        return PaperExec(
            mirror=False,
            market="futures",
            interval=settings.paper_market_data_interval or settings.market_data_interval,
            leverage=Decimal(str(settings.paper_leverage)),
            taker_fee=Decimal(str(settings.paper_taker_fee)),
            maker_fee=Decimal(str(settings.paper_maker_fee)),
            funding_enabled=bool(settings.funding_cost_enabled),
            allow_short=bool(settings.momentum_allow_short),
            risk_pct=Decimal(str(settings.paper_position_risk_pct)),
            atr_stop_multiplier=Decimal(str(settings.paper_atr_stop_multiplier)),
            tp_rr=Decimal(str(settings.paper_tp_rr)),
            notional_cap_pct=Decimal(str(settings.paper_max_capital_per_trade_pct)),
            daily_max_loss_pct=Decimal(str(settings.paper_max_daily_loss_pct)),
            max_drawdown_pct=Decimal(str(settings.paper_max_drawdown_pct)),
            max_open_positions=0,        # 0 => keep the account's own column value
            max_exposure_pct=Decimal("0"),
        )

    # Mirror the live account's economics.
    is_futures = settings.trading_market.lower() == "futures"
    ss = StrategySettingsRepository(db).current()
    live_daily_loss = Decimal(str(ss.daily_max_loss_pct))
    live_drawdown = Decimal(str(settings.max_account_drawdown_pct))
    # Paper is a simulation whose purpose is to OBSERVE behaviour, so the auto-
    # pause hard stops relax to the LOOSER of paper_* and live when the flag is
    # on (default). Sizing/exposure/positions/timeframe still mirror live
    # exactly — only the two hard-pause thresholds relax, so paper keeps trading
    # through drawdowns that would halt live. Turn off the flag to inherit the
    # strict live thresholds verbatim.
    if getattr(settings, "paper_relax_mirror_limits", True):
        paper_daily = Decimal(str(settings.paper_max_daily_loss_pct))
        paper_dd = Decimal(str(settings.paper_max_drawdown_pct))
        daily_max_loss_pct = max(live_daily_loss, paper_daily)
        max_drawdown_pct = max(live_drawdown, paper_dd)
    else:
        daily_max_loss_pct = live_daily_loss
        max_drawdown_pct = live_drawdown
    return PaperExec(
        mirror=True,
        market="futures" if is_futures else "spot",
        interval=settings.market_data_interval,
        leverage=Decimal(str(settings.futures_leverage)) if is_futures else Decimal("1"),
        taker_fee=Decimal(str(settings.paper_taker_fee if is_futures else settings.paper_spot_taker_fee)),
        maker_fee=Decimal(str(settings.paper_maker_fee if is_futures else settings.paper_spot_maker_fee)),
        # Spot longs have no funding; futures perps do.
        funding_enabled=bool(settings.funding_cost_enabled) if is_futures else False,
        # Live spot skips shorts; futures mirrors the strategy's allow_short.
        allow_short=bool(settings.momentum_allow_short) if is_futures else False,
        risk_pct=Decimal(str(settings.max_risk_per_trade_pct)),
        atr_stop_multiplier=Decimal(str(ss.atr_multiplier)),
        tp_rr=Decimal(str(ss.min_reward_risk)),
        notional_cap_pct=Decimal(str(ss.max_capital_per_trade_pct)),
        daily_max_loss_pct=daily_max_loss_pct,
        max_drawdown_pct=max_drawdown_pct,
        max_open_positions=int(ss.max_open_positions),
        max_exposure_pct=Decimal(str(settings.max_total_exposure_pct)),
    )
