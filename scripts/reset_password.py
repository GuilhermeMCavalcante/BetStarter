"""Reset password for an existing user.

Usage:
    python scripts/reset_password.py --username admin --password "NewPass1"
    python scripts/reset_password.py --username admin          # prompts securely
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
from app.services.auth import change_password, get_user

init_db()

parser = argparse.ArgumentParser(description="Reset a BetStarter user password.")
parser.add_argument("--username", default="admin", help="Username (default: admin)")
parser.add_argument("--password", default="", help="New password (prompted if omitted)")
args = parser.parse_args()

with SessionLocal() as db:
    user = get_user(db, args.username)
    if not user:
        print(f"[ERROR] User '{args.username}' not found.")
        sys.exit(1)

    password = args.password or getpass.getpass(f"New password for '{args.username}': ")

    try:
        change_password(db, user.id, password)
        print(f"[OK] Password for '{user.username}' (role={user.role}) updated successfully.")
        print("     Account lockout has been cleared.")
    except ValueError as e:
        print(f"[ERROR] {e}")
        print("       Requirements: min 8 chars, 1 uppercase letter, 1 number.")
        sys.exit(1)
