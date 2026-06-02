from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.enums import UserRole

DbSession = Annotated[Session, Depends(get_db)]
bearer = HTTPBearer(auto_error=False)


def current_user_role(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> UserRole:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    try:
        payload = decode_access_token(credentials.credentials)
        if payload.get("type") not in (None, "access"):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        return UserRole(payload.get("role", UserRole.viewer))
    except (InvalidTokenError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from None


def require_admin(role: Annotated[UserRole, Depends(current_user_role)]) -> None:
    if role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
