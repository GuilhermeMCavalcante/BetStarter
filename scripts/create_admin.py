"""Bootstrap script — creates the first admin user.

Usage:
    python scripts/create_admin.py
    python scripts/create_admin.py --username myname --password "MyPass1"

If --password is omitted, the script will prompt securely (no echo).
"""
import argparse
import getpass
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.services.auth import create_user, get_user

init_db()

parser = argparse.ArgumentParser(description="Create first admin user for BetStarter.")
parser.add_argument("--username", default="admin", help="Admin username (default: admin)")
parser.add_argument("--email", default="", help="Admin email (optional)")
parser.add_argument("--password", default="", help="Admin password (prompted if omitted)")
args = parser.parse_args()

with SessionLocal() as db:
    existing = get_user(db, args.username)
    if existing:
        print(f"[SKIP] User '{existing.username}' already exists (role={existing.role}).")
        sys.exit(0)

    password = args.password or getpass.getpass(f"Password for '{args.username}': ")

    try:
        user = create_user(
            db,
            username=args.username,
            password=password,
            role="admin",
            email=args.email or None,
        )
        print(f"[OK] Admin user '{user.username}' created successfully.")
        print("     IMPORTANT: change the password after first login.")
    except ValueError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
