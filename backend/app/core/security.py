from datetime import UTC, datetime, timedelta

import jwt
from cryptography.fernet import Fernet, InvalidToken
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(subject: str, role: str) -> str:
    settings = get_settings()
    expires = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "role": role, "exp": expires}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict:
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
        return value
