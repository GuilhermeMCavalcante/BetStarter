import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.db.session import SessionLocal
from app.models.entities import Odd

with SessionLocal() as db:
    rows = db.query(Odd).limit(100).all()

    print(f"Total amostra: {len(rows)}")
    print("-" * 80)

    for o in rows:
        print({
            "fixture_id": o.fixture_id,
            "bookmaker": o.bookmaker,
            "market": o.market,
            "selection": o.selection,
            "odd": o.odd,
        })