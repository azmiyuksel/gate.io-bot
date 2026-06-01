from sqlalchemy.orm import Session

from app.models.entities import PaperAccount, PaperOrder
from app.models.enums import PaperOrderStatus
from app.paper_trading.broker import PaperBroker
from app.paper_trading.models import MarketData, TradingSignal


class PaperOrderManager:
    def __init__(self, db: Session, account: PaperAccount) -> None:
        self.db = db
        self.account = account
        self.broker = PaperBroker(db, account)
        self._last_signal_key: str | None = None

    def execute_signal(self, signal: TradingSignal, quantity, data: MarketData) -> PaperOrder | None:
        signal_key = f"{signal.strategy}:{signal.symbol}:{signal.side}:{int(signal.timestamp.timestamp())}"
        if signal_key == self._last_signal_key:
            return None
        self._last_signal_key = signal_key
        return self.broker.submit_signal(signal, quantity, data)

    def pending_orders(self) -> list[PaperOrder]:
        return (
            self.db.query(PaperOrder)
            .filter(PaperOrder.account_id == self.account.id, PaperOrder.status == PaperOrderStatus.pending)
            .all()
        )
