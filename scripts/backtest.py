import sys
import argparse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.config import validate_world_cup_scope
from app.db.session import SessionLocal
from app.services.backtester import run_backtest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bookmaker", default="Superbet")
    parser.add_argument("--stake", type=float, default=1.0)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    league, season = validate_world_cup_scope()

    with SessionLocal() as db:
        result = run_backtest(
            db,
            league=league,
            season=season,
            bookmaker=args.bookmaker,
            stake=args.stake,
            debug=args.debug,
        )

    print(result)


if __name__ == "__main__":
    main()