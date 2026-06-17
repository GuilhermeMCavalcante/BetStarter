import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.db.session import SessionLocal
from app.models.entities import Fixture, Odd

with SessionLocal() as db:
    fixtures = db.query(Fixture).limit(30).all()

    print("FIXTURES")
    print("-" * 80)

    for f in fixtures:
        count_odds = db.query(Odd).filter(Odd.fixture_id == f.fixture_id).count()
        print({
            "fixture_id": f.fixture_id,
            "date": f.date,
            "home": f.home_team,
            "away": f.away_team,
            "league": f.league,
            "season": f.season,
            "odds": count_odds,
        })