import sys
import argparse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.db.session import SessionLocal
from app.models.entities import Fixture, TeamRecentStat


def build_stats(fixtures, team_id):
    played = []

    for f in fixtures:
        if f.home_team_id == team_id:
            gf = f.home_goals
            ga = f.away_goals
        elif f.away_team_id == team_id:
            gf = f.away_goals
            ga = f.home_goals
        else:
            continue

        played.append((gf, ga))

    if not played:
        return None

    matches = len(played)

    goals_for_avg = sum(x[0] for x in played) / matches
    goals_against_avg = sum(x[1] for x in played) / matches

    btts_rate = (
        sum(1 for gf, ga in played if gf > 0 and ga > 0)
        / matches
    )

    over15_rate = (
        sum(1 for gf, ga in played if gf + ga >= 2)
        / matches
    )

    over25_rate = (
        sum(1 for gf, ga in played if gf + ga >= 3)
        / matches
    )

    return {
        "matches": matches,
        "goals_for_avg": goals_for_avg,
        "goals_against_avg": goals_against_avg,
        "btts_rate": btts_rate,
        "over15_rate": over15_rate,
        "over25_rate": over25_rate,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2022)
    args = parser.parse_args()

    with SessionLocal() as db:

        db.query(TeamRecentStat).filter(
            TeamRecentStat.league_id == 1,
            TeamRecentStat.season == args.season,
        ).delete()

        fixtures = (
            db.query(Fixture)
            .filter(
                Fixture.league_id == 1,
                Fixture.season == args.season,
                Fixture.home_goals.isnot(None),
                Fixture.away_goals.isnot(None),
            )
            .order_by(Fixture.date.asc())
            .all()
        )

        teams = {}

        for fixture in fixtures:

            for team_id in [
                fixture.home_team_id,
                fixture.away_team_id,
            ]:

                previous_games = [
                    f
                    for f in fixtures
                    if f.date < fixture.date
                    and (
                        f.home_team_id == team_id
                        or f.away_team_id == team_id
                    )
                ]

                stats = build_stats(previous_games, team_id)

                if not stats:
                    continue

                teams[(team_id, fixture.date)] = stats

        print("Stats históricas geradas:", len(teams))


if __name__ == "__main__":
    main()