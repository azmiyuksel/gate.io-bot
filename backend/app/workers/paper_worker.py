import asyncio

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.entities import PaperAccount
from app.paper_trading.engine import PaperTradingEngine
from app.paper_trading.strategy_adapter import CapitalPreservationAdapter


async def main() -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        account = db.query(PaperAccount).filter(PaperAccount.name == "default").first()
        if account is None:
            account = PaperAccount()
            db.add(account)
            db.commit()
            db.refresh(account)
        strategy = CapitalPreservationAdapter()
        engine = PaperTradingEngine(db, account, strategy=strategy)
        await engine.start(settings.symbols)
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
