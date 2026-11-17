"""Explicit development-only account provisioning; no default accounts or HTTP registration."""

import argparse
import getpass
import sys
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from ..db import get_engine
from .config import AuthSettings
from .service import create_user


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-user")
    create.add_argument("--username", required=True)
    create.add_argument("--display-name", required=True)
    create.add_argument("--role", choices=["administrator", "analyst", "viewer"], required=True)
    create.add_argument("--password-stdin", action="store_true")
    args = parser.parse_args()
    if AuthSettings().app_env != "development":
        parser.error("Account provisioning requires APP_ENV=development")
    password = (
        sys.stdin.readline().rstrip("\r\n") if args.password_stdin else getpass.getpass("New password: ")
    )
    with Session(get_engine()) as db, db.begin():
        user = create_user(db, args.username, args.display_name, args.role, password)
        print(f"Created {user.username} ({user.role})")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, SQLAlchemyError):
        print(
            "Account provisioning failed. Check configuration, password policy and username uniqueness.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
