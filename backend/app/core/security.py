import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


def _to_bcrypt_bytes(password: str) -> bytes:
    # bcrypt only considers the first 72 bytes; truncate explicitly so longer
    # passwords don't raise on bcrypt >= 5 (and stay stable across versions).
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_to_bcrypt_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_to_bcrypt_bytes(password), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(subject: str, role: str) -> str:
    settings = get_settings()
    expires = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "role": role, "type": "access", "exp": expires}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def create_refresh_token(subject: str) -> tuple[str, str, datetime]:
    """Return (encoded token, jti, expiry) for a new refresh token.

    The ``jti`` is persisted server-side so the token can be revoked.
    """
    settings = get_settings()
    expires = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
    jti = uuid.uuid4().hex
    payload = {"sub": subject, "type": "refresh", "jti": jti, "exp": expires}
    token = jwt.encode(payload, settings.secret_key, algorithm="HS256")
    return token, jti, expires


def decode_access_token(token: str) -> dict:
    payload = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Token is not an access token")
    return payload


def decode_token(token: str) -> dict:
    """Decode any JWT issued by this service (access or refresh)."""
    return jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])


def get_cipher() -> Fernet | None:
    key = get_settings().fernet_key
    if not key:
        return None
    return Fernet(key.encode())


def encrypt_secret(value: str) -> str:
    cipher = get_cipher()
    if cipher is None:
        return value
    return cipher.encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    cipher = get_cipher()
    if cipher is None:
        return value
    try:
        return cipher.decrypt(value.encode()).decode()
    except InvalidToken:
        import logging
        logging.getLogger(__name__).warning(
            "Fernet decrypt failed — value may have been stored before FERNET_KEY was set. "
            "Returning raw value as fallback."
        )
        return value
