import argparse

from app.core.security import hash_password
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models.entities import User
from app.models.enums import UserRole


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == args.email).first()
        if existing:
            existing.password_hash = hash_password(args.password)
            existing.role = UserRole.admin
        else:
            db.add(User(email=args.email, password_hash=hash_password(args.password), role=UserRole.admin))
        db.commit()
        print(f"Admin user ready: {args.email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
