from datetime import UTC, datetime
from io import StringIO

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backtest.broker import VirtualBroker
from app.backtest.metrics import compute_metrics, monte_carlo
from app.backtest.models import BacktestConfig, SUPPORTED_TIMEFRAMES, TIMEFRAME_TO_PANDAS
from app.backtest.portfolio import Portfolio
from app.backtest.reports import build_plotly_report
from app.backtest.strategy_runner import EmaRsiAtrStrategy
from app.models.entities import HistoricalCandle
from app.services.exchange.gateio import GateIOClient


class HistoricalDataLoader:
    def __init__(self, db: Session, gateio: GateIOClient | None = None) -> None:
        self.db = db
        self.gateio = gateio

    def load_from_cache(self, symbol: str, timeframe: str, start_at: datetime, end_at: datetime) -> pd.DataFrame:
        rows = self.db.scalars(
            select(HistoricalCandle)
            .where(HistoricalCandle.symbol == symbol)
            .where(HistoricalCandle.timeframe == timeframe)
            .where(HistoricalCandle.timestamp >= start_at)
            .where(HistoricalCandle.timestamp <= end_at)
            .order_by(HistoricalCandle.timestamp.asc())
        ).all()
        return self.validate(
            pd.DataFrame(
                [
                    {
                        "timestamp": row.timestamp,
                        "open": float(row.open),
                        "high": float(row.high),
                        "low": float(row.low),
                        "close": float(row.close),
                        "volume": float(row.volume),
                    }
                    for row in rows
                ]
            ),
            timeframe,
        )

    async def load_from_gateio(
        self, symbol: str, timeframe: str, start_at: datetime, end_at: datetime
    ) -> pd.DataFrame:
        if self.gateio is None:
            raise ValueError("Gate.io client is required")
        candles = await self.gateio.candles(symbol, interval=timeframe, limit=1000)
        frame = pd.DataFrame(candles)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="s", utc=True)
        frame = frame[(frame["timestamp"] >= start_at) & (frame["timestamp"] <= end_at)]
        frame = self.validate(frame, timeframe)
        self.cache(frame, symbol, timeframe, "gateio")
        return frame

    def load_from_csv(self, csv_text: str, timeframe: str) -> pd.DataFrame:
        return self.validate(pd.read_csv(StringIO(csv_text)), timeframe)

    def validate(self, frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        if timeframe not in SUPPORTED_TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        if frame.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"Missing OHLCV columns: {sorted(missing)}")
        clean = frame.copy()
        clean["timestamp"] = pd.to_datetime(clean["timestamp"], utc=True)
        clean = clean.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
        clean = clean.set_index("timestamp")
        for column in ["open", "high", "low", "close", "volume"]:
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
        clean = clean.dropna(subset=["open", "high", "low", "close"])
        clean = clean[~clean.index.duplicated(keep="last")]
        expected = pd.date_range(clean.index.min(), clean.index.max(), freq=TIMEFRAME_TO_PANDAS[timeframe])
        missing_candles = expected.difference(clean.index)
        clean.attrs["missing_candles"] = [timestamp.isoformat() for timestamp in missing_candles]
        return clean

    def cache(self, frame: pd.DataFrame, symbol: str, timeframe: str, source: str) -> None:
        for timestamp, row in frame.iterrows():
            exists = self.db.scalar(
                select(HistoricalCandle.id)
                .where(HistoricalCandle.symbol == symbol)
                .where(HistoricalCandle.timeframe == timeframe)
                .where(HistoricalCandle.timestamp == timestamp.to_pydatetime())
            )
            if exists:
                continue
            self.db.add(
                HistoricalCandle(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=timestamp.to_pydatetime(),
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row["volume"],
                    source=source,
                )
            )
        self.db.commit()


class BacktestEngine:
    def run(self, data: pd.DataFrame, config: BacktestConfig) -> dict:
        if data.empty:
            raise ValueError("No historical data available for backtest")
        strategy = EmaRsiAtrStrategy(config.parameters)
        prepared = strategy.prepare(data)
        portfolio = Portfolio(config.initial_cash)
        broker = VirtualBroker(
            portfolio,
            commission_rate=config.commission_rate,
            slippage_rate=config.slippage_rate,
            spread_rate=config.spread_rate,
            order_latency_candles=config.order_latency_candles,
        )
        for _, candle in prepared.iterrows():
            broker.process_orders(candle)
            broker.manage_exits(candle, float(config.parameters.get("trailing_stop_pct", 0.01)))
            strategy.on_candle(candle)
            equity = portfolio.equity_curve[-1]["equity"] if portfolio.equity_curve else config.initial_cash
            if not portfolio.can_open(config.max_open_positions):
                continue
            if strategy.should_buy():
                entry = float(candle["open"])
                quantity = strategy.position_size(equity, entry)
                stop_loss, take_profit = strategy.risk_levels(entry)
                if stop_loss > 0 and quantity > 0:
                    broker.market_buy(candle, config.symbol, quantity, stop_loss, take_profit)
            portfolio.mark_to_market(candle.name, float(candle["close"]))

        for position in list(portfolio.positions):
            last = prepared.iloc[-1]
            broker._close(position, last, float(last["close"]), "end_of_test")

        metrics = compute_metrics(portfolio.equity_curve, portfolio.closed_trades)
        charts = build_plotly_report(portfolio.equity_curve, portfolio.closed_trades)
        mc = monte_carlo(portfolio.closed_trades, config.initial_cash, scenarios=1000)
        return {
            "metrics": metrics,
            "charts": charts,
            "monte_carlo": mc,
            "trades": portfolio.closed_trades,
            "completed_at": datetime.now(UTC),
        }
