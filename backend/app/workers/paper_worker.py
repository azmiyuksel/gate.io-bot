import asyncio
import logging

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.models.entities import PaperAccount
from app.paper_trading.engine import PaperTradingEngine
from app.paper_trading.portfolio import PaperPortfolio
from app.paper_trading.strategy_adapter import CapitalPreservationAdapter

logger = logging.getLogger(__name__)


async def main() -> None:
    configure_logging()
    settings = get_settings()
    db = SessionLocal()
    try:
        account = db.query(PaperAccount).filter(PaperAccount.name == "default").first()
        if account is None:
            account = PaperAccount()
            db.add(account)
            db.commit()
            db.refresh(account)
        # Reset cash_balance if it was drained to 0
        try:
            if account.cash_balance <= 0:
                logger.warning("Paper account cash_balance was %s, resetting to initial_balance", account.cash_balance)
                account.cash_balance = account.initial_balance
                account.realized_pnl = 0
                db.commit()
        except (TypeError, AttributeError):
            pass
        # Record initial equity point so the chart is never empty
        portfolio = PaperPortfolio(db, account)
        portfolio.record_equity()
        db.commit()
        logger.info("Paper worker starting: account=%s cash=%s status=%s", account.id, account.cash_balance, account.status)
        strategy = CapitalPreservationAdapter()
        engine = PaperTradingEngine(db, account, strategy=strategy)
        await engine.start(settings.symbols)
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
