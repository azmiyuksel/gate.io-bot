from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import DbSession
from app.core.config import get_settings
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.entities import RefreshToken, User
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])

_settings = get_settings()
_login_limiter = SlidingWindowRateLimiter(
    _settings.login_rate_limit_attempts, _settings.login_rate_limit_window_seconds
)


def _issue_tokens(db: DbSession, user: User) -> TokenResponse:
    access = create_access_token(str(user.id), user.role)
    refresh, jti, expires = create_refresh_token(str(user.id))
    db.add(RefreshToken(jti=jti, user_id=user.id, expires_at=expires))
    db.commit()
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DbSession, request: Request) -> TokenResponse:
    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"{client_ip}:{payload.email.lower()}"
    if not _login_limiter.is_allowed(rate_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts, try again later",
        )
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    # Successful auth clears the throttle for this key.
    _login_limiter.reset(rate_key)
    return _issue_tokens(db, user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: DbSession) -> TokenResponse:
    try:
        claims = decode_token(payload.refresh_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from None
    if claims.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    record = db.scalar(select(RefreshToken).where(RefreshToken.jti == claims.get("jti")))
    if record is None or record.revoked:
        raise HTTPException(status_code=401, detail="Refresh token revoked")

    user = db.get(User, int(claims["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User inactive")

    # Rotate: revoke the presented token and issue a fresh pair.
    record.revoked = True
    db.commit()
    return _issue_tokens(db, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: RefreshRequest, db: DbSession) -> None:
    try:
        claims = decode_token(payload.refresh_token)
    except Exception:
        return  # Nothing to revoke for an unparseable token.
    record = db.scalar(select(RefreshToken).where(RefreshToken.jti == claims.get("jti")))
    if record is not None and not record.revoked:
        record.revoked = True
        db.commit()


def purge_expired_refresh_tokens(db: DbSession) -> int:
    """Delete refresh tokens past their expiry; returns the number removed."""
    rows = db.query(RefreshToken).filter(RefreshToken.expires_at < datetime.now(UTC)).all()
    for row in rows:
        db.delete(row)
    db.commit()
    return len(rows)
