from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.account.engine import AccountManager
from app.api.deps import DbSession, current_user_role, require_admin
from app.models.entities import AccountSnapshot
from app.schemas.account import AccountSnapshotOut, EquityOut
from app.services.exchange.gateio import GateIOClient

router = APIRouter(prefix="/account", tags=["account"], dependencies=[Depends(current_user_role)])


@router.get("/snapshot", response_model=AccountSnapshotOut)
def latest_snapshot(db: DbSession) -> AccountSnapshot:
    snapshot = AccountManager(db).last_snapshot()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No account snapshot yet")
    return snapshot


@router.get("/equity", response_model=EquityOut)
def equity(db: DbSession) -> EquityOut:
    manager = AccountManager(db)
    last = manager.last_snapshot()
    return EquityOut(
        total_equity=manager.latest_equity(),
        peak_equity=manager.peak_equity(),
        drawdown_pct=manager.drawdown_pct(),
        source=last.source if last else "fallback",
    )


@router.get("/history", response_model=List[AccountSnapshotOut])
def history(db: DbSession, limit: int = 200) -> List[AccountSnapshot]:
    return (
        db.query(AccountSnapshot)
        .order_by(AccountSnapshot.created_at.desc())
        .limit(min(limit, 1000))
        .all()
    )


@router.post("/refresh", response_model=AccountSnapshotOut, dependencies=[Depends(require_admin)])
async def refresh(db: DbSession) -> AccountSnapshot:
    client = GateIOClient()
    try:
        return await AccountManager(db, client).refresh()
    finally:
        await client.close()
