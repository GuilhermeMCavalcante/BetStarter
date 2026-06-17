import sys
import argparse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.services.api_football import ApiFootballClient


def evaluate_over15(home_goals, away_goals):
    return (home_goals + away_goals) >= 2


def evaluate_over25(home_goals, away_goals):
    return (home_goals + away_goals) >= 3


def evaluate_btts(home_goals, away_goals):
    return home_goals > 0 and away_goals > 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2022)
    args = parser.parse_args()

    client = ApiFootballClient()

    fixtures = client.fixtures_range(
        league=1,
        season=args.season,
        date_from=f"{args.season}-01-01",
        date_to=f"{args.season}-12-31",
    )

    over15_total = 0
    over15_hits = 0

    over25_total = 0
    over25_hits = 0

    btts_total = 0
    btts_hits = 0

    for item in fixtures:
        goals = item.get("goals", {})

        home = goals.get("home")
        away = goals.get("away")

        if home is None or away is None:
            continue

        over15_total += 1
        if evaluate_over15(home, away):
            over15_hits += 1

        over25_total += 1
        if evaluate_over25(home, away):
            over25_hits += 1

        btts_total += 1
        if evaluate_btts(home, away):
            btts_hits += 1

    print()
    print("=" * 60)
    print(f"WORLD CUP {args.season}")
    print("=" * 60)

    print()
    print("OVER 1.5")
    print("Entradas:", over15_total)
    print("Acertos:", over15_hits)
    print("Hit Rate:", round(over15_hits / over15_total * 100, 2), "%")

    print()
    print("OVER 2.5")
    print("Entradas:", over25_total)
    print("Acertos:", over25_hits)
    print("Hit Rate:", round(over25_hits / over25_total * 100, 2), "%")

    print()
    print("BTTS")
    print("Entradas:", btts_total)
    print("Acertos:", btts_hits)
    print("Hit Rate:", round(btts_hits / btts_total * 100, 2), "%")


if __name__ == "__main__":
    main()