import asyncio
import logging

from sqlalchemy.exc import OperationalError

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.models.entities import PaperAccount
from app.models.enums import PaperBotStatus
from app.paper_trading.engine import PaperTradingEngine
from app.paper_trading.portfolio import PaperPortfolio
from app.paper_trading.strategy_adapter import CapitalPreservationAdapter

logger = logging.getLogger(__name__)

MAX_RETRY_DELAY = 60  # seconds


async def main() -> None:
    configure_logging()
    settings = get_settings()
    retry_delay = 1
    while True:
        db = SessionLocal()
        try:
            account = db.query(PaperAccount).filter(PaperAccount.name == "default").first()
            if account is None:
                account = PaperAccount()
                db.add(account)
                db.commit()
                db.refresh(account)
            try:
                if account.cash_balance <= 0:
                    logger.warning("Paper account cash_balance was %s, resetting to initial_balance", account.cash_balance)
                    account.cash_balance = account.initial_balance
                    account.realized_pnl = 0
                    db.commit()
            except (TypeError, AttributeError):
                pass
            portfolio = PaperPortfolio(db, account)
            portfolio.record_equity()
            db.commit()
            logger.info("Paper worker starting: account=%s cash=%s status=%s", account.id, account.cash_balance, account.status)
            strategy = CapitalPreservationAdapter()
            engine = PaperTradingEngine(db, account, strategy=strategy)
            # Only start if the account status is RUNNING (not stopped by user)
            if account.status == PaperBotStatus.running:
                await engine.start(settings.symbols)
            else:
                logger.info("Paper worker: account not running (status=%s), waiting for start signal", account.status)
                while account.status != PaperBotStatus.running:
                    await asyncio.sleep(5)
                    try:
                        db.refresh(account)
                    except Exception:
                        pass
                db.close()
                continue
            break
        except (OperationalError, OSError) as exc:
            logger.warning("Paper worker connection error (retry in %ss): %s", retry_delay, exc)
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
        except Exception as exc:
            logger.error("Paper worker fatal error, restarting: %s", exc)
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
        finally:
            try:
                db.close()
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())
