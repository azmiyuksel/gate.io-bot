"""Audit trail helper: records privileged actions attributed to a user."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.entities import AuditLog

logger = get_logger("app.audit")


def record_audit(db: Session, actor: str, action: str, detail: str | None = None) -> None:
    """Persist an audit entry and mirror it to the structured log."""
    db.add(AuditLog(actor=actor, action=action, detail=detail))
    db.commit()
    logger.info("audit", extra={"actor": actor, "action": action, "detail": detail})
