"""Creates (or resets the password of) an authority staff account.

Usage, from the repository root:
    .venv/bin/python -m backend.scripts.create_staff staff@example.org
The password is prompted for and never echoed or logged.
"""

import asyncio
import getpass
import sys

import sqlalchemy as sa

from backend.db.session import async_session_factory
from backend.models.authority import STAFF_ROLE, StaffUser
from backend.services.authority.auth import hash_password

MIN_PASSWORD_LENGTH = 12


async def upsert_staff(email: str, password: str) -> str:
    email = email.strip().lower()
    async with async_session_factory() as session:
        user = await session.scalar(sa.select(StaffUser).where(StaffUser.email == email))
        if user is None:
            session.add(StaffUser(email=email, password_hash=hash_password(password), role=STAFF_ROLE, is_active=True))
            outcome = "created"
        else:
            user.password_hash = hash_password(password)
            user.is_active = True
            outcome = "password reset"
        await session.commit()
    return outcome


def main() -> None:
    if len(sys.argv) != 2 or "@" not in sys.argv[1]:
        sys.exit("usage: python -m backend.scripts.create_staff <email>")
    password = getpass.getpass("Password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        sys.exit(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    if getpass.getpass("Repeat password: ") != password:
        sys.exit("passwords do not match")
    print(f"{sys.argv[1]}: {asyncio.run(upsert_staff(sys.argv[1], password))}")


if __name__ == "__main__":
    main()
