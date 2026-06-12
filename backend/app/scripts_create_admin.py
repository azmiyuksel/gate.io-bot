import argparse
import getpass
import re
import sys

from app.core.security import hash_password
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models.entities import User
from app.models.enums import UserRole


def validate_password(password: str) -> None:
    if len(password) < 8:
        print("Error: Password must be at least 8 characters.", file=sys.stderr)
        sys.exit(1)
    if not re.search(r"[A-Z]", password):
        print("Error: Password must contain at least one uppercase letter.", file=sys.stderr)
        sys.exit(1)
    if not re.search(r"[a-z]", password):
        print("Error: Password must contain at least one lowercase letter.", file=sys.stderr)
        sys.exit(1)
    if not re.search(r"\d", password):
        print("Error: Password must contain at least one digit.", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", default=None, help="Password (interactive prompt used if omitted)")
    args = parser.parse_args()

    password = args.password
    if password is None:
        password = getpass.getpass("Enter admin password: ")
        confirm = getpass.getpass("Confirm admin password: ")
        if password != confirm:
            print("Passwords do not match.")
            return

    validate_password(password)

    init_db()
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == args.email).first()
        if existing:
            existing.password_hash = hash_password(password)
            existing.role = UserRole.admin
        else:
            db.add(User(email=args.email, password_hash=hash_password(password), role=UserRole.admin))
        db.commit()
        print(f"Admin user ready: {args.email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
