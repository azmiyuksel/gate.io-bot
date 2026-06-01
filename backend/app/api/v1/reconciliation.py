from typing import List

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, current_user_role, require_admin
from app.models.entities import ReconciliationLog
from app.models.enums import ReconcileAction
from app.reconciliation.engine import ReconciliationEngine
from app.schemas.reconciliation import ReconciliationLogOut, ReconciliationRunOut
from app.services.exchange.gateio import GateIOClient

router = APIRouter(
    prefix="/reconciliation", tags=["reconciliation"], dependencies=[Depends(current_user_role)]
)


@router.get("/logs", response_model=List[ReconciliationLogOut])
def logs(db: DbSession, limit: int = 100) -> List[ReconciliationLog]:
    return (
        db.query(ReconciliationLog)
        .order_by(ReconciliationLog.created_at.desc())
        .limit(min(limit, 1000))
        .all()
    )


@router.post("/run", response_model=ReconciliationRunOut, dependencies=[Depends(require_admin)])
async def run(db: DbSession) -> ReconciliationRunOut:
    client = GateIOClient()
    try:
        results = await ReconciliationEngine(db, client).reconcile_open_orders()
    finally:
        await client.close()
    changed = [r for r in results if r.action != ReconcileAction.no_change]
    return ReconciliationRunOut(reconciled=len(results), changed=len(changed), logs=results)
