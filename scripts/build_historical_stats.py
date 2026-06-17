import sys
import argparse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.session import SessionLocal
from app.models.entities import Fixture, HistoricalTeamStat


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

        if gf is None or ga is None:
            continue

        played.append((gf, ga))

    if not played:
        return None

    matches = len(played)

    return {
        "matches": matches,
        "goals_for_avg": sum(x[0] for x in played) / matches,
        "goals_against_avg": sum(x[1] for x in played) / matches,
        "btts_rate": sum(1 for gf, ga in played if gf > 0 and ga > 0) / matches,
        "over15_rate": sum(1 for gf, ga in played if gf + ga >= 2) / matches,
        "over25_rate": sum(1 for gf, ga in played if gf + ga >= 3) / matches,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2022)
    args = parser.parse_args()

    with SessionLocal() as db:
        db.query(HistoricalTeamStat).filter(
            HistoricalTeamStat.league_id == 1,
            HistoricalTeamStat.season == args.season,
        ).delete(synchronize_session=False)

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

        created = 0

        for fixture in fixtures:
            for team_id in [fixture.home_team_id, fixture.away_team_id]:
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

                values = {
                    "fixture_id": fixture.id,
                    "team_id": team_id,
                    "league_id": fixture.league_id,
                    "season": fixture.season,
                    **stats,
                }

                stmt = sqlite_insert(HistoricalTeamStat).values(**values)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["fixture_id", "team_id"],
                    set_=values,
                )

                db.execute(stmt)
                created += 1

        db.commit()

    print({
        "season": args.season,
        "historical_stats_created": created,
    })


if __name__ == "__main__":
    main()