import sys
import argparse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.db.session import SessionLocal
from app.services.api_football import ApiFootballClient
from app.services.collector import upsert_fixture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2022)
    args = parser.parse_args()

    client = ApiFootballClient()

    rows = client.fixtures_range(
        league=1,
        season=args.season,
        date_from=f"{args.season}-01-01",
        date_to=f"{args.season}-12-31",
    )

    with SessionLocal() as db:
        for row in rows:
            upsert_fixture(db, row, league_id=1, season=args.season)

        db.commit()

    print({
        "competition": "FIFA World Cup",
        "season": args.season,
        "fixtures_imported": len(rows),
    })


if __name__ == "__main__":
    main()