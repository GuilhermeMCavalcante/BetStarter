from __future__ import annotations

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.models.entities import Fixture, Odd, TeamRecentStat
from app.services.api_football import ApiFootballClient
from zoneinfo import ZoneInfo
BR_TZ = ZoneInfo("America/Sao_Paulo")

def parse_dt(value: str | None):
    if not value:
        return None

    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    dt_br = dt.astimezone(BR_TZ)

    return dt_br.replace(tzinfo=None)


def upsert_fixture(db: Session, item: dict, league_id: int, season: int) -> None:
    fixture = item["fixture"]
    fixture_id = fixture["id"]
    teams = item["teams"]
    goals = item.get("goals", {})

    values = {
        "id": fixture_id,
        "api_fixture_id": fixture_id,
        "league_id": league_id,
        "season": season,
        "date": parse_dt(fixture.get("date")),
        "status": fixture.get("status", {}).get("short"),
        "home_team_id": teams["home"]["id"],
        "away_team_id": teams["away"]["id"],
        "home_team": teams["home"]["name"],
        "away_team": teams["away"]["name"],
        "home_goals": goals.get("home"),
        "away_goals": goals.get("away"),
    }
    stmt = sqlite_insert(Fixture).values(**values)
    stmt = stmt.on_conflict_do_update(index_elements=["api_fixture_id"], set_=values)
    db.execute(stmt)


def fetch_and_store_fixtures(db: Session, league: int, season: int, days: int = 3, past_days: int = 0) -> int:
    client = ApiFootballClient()

    date_from = (datetime.now(BR_TZ).date() - timedelta(days=past_days)).isoformat()
    date_to = (datetime.now(BR_TZ).date() + timedelta(days=days)).isoformat()

    rows = client.fixtures_range(
        league=league,
        season=season,
        date_from=date_from,
        date_to=date_to,
        timezone="America/Sao_Paulo",
    )

    for row in rows:
        upsert_fixture(db, row, league, season)

    db.commit()
    return len(rows)


def fetch_and_store_odds(db: Session, league: int, season: int, bookmaker: int | None = None) -> int:
    client = ApiFootballClient()
    rows = client.odds(league=league, season=season, bookmaker=bookmaker)
    count = 0
    for item in rows:
        fixture_id = item["fixture"]["id"]
        for bookmaker_item in item.get("bookmakers", []):
            bookmaker_name = bookmaker_item.get("name", "Unknown")
            for bet in bookmaker_item.get("bets", []):
                market = normalize_market(bet.get("name", ""))
                if market not in {"Over/Under", "Both Teams Score", "Match Winner"}:
                    continue
                for value in bet.get("values", []):
                    selection = normalize_selection(market, value.get("value", ""))
                    if selection not in {"Over 1.5", "Under 1.5", "Over 2.5", "Under 2.5", "Yes", "No", "Home", "Draw", "Away"}:
                        continue
                    try:
                        odd_value = float(value.get("odd"))
                    except (TypeError, ValueError):
                        continue
                    stmt = sqlite_insert(Odd).values(
                        fixture_id=fixture_id,
                        bookmaker=bookmaker_name,
                        market=market,
                        selection=selection,
                        odd=odd_value,
                        updated_at=datetime.utcnow(),
                    )
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["fixture_id", "bookmaker", "market", "selection"],
                        set_={"odd": odd_value, "updated_at": datetime.utcnow()},
                    )
                    db.execute(stmt)
                    count += 1
    db.commit()
    return count


def normalize_market(market):
    m = str(market).strip().lower()

    if m in [
        "goals over/under",
        "over/under",
        "total goals",
        "goals over under",
    ]:
        return "Over/Under"

    if m in [
        "both teams score",
        "both teams to score",
        "btts",
    ]:
        return "Both Teams Score"

    if m in [
        "match winner",
        "winner",
        "1x2",
        "fulltime result",
    ]:
        return "Match Winner"

    if m in [
        "double chance",
    ]:
        return "Double Chance"

    return str(market).strip()

def normalize_selection(market, value):
    v = str(value).strip()

    if market == "Over/Under":
        low = v.lower()

        if low in ["over 1.5", "1.5 over"]:
            return "Over 1.5"
        if low in ["over 2.5", "2.5 over"]:
            return "Over 2.5"
        if low in ["under 1.5", "1.5 under"]:
            return "Under 1.5"
        if low in ["under 2.5", "2.5 under"]:
            return "Under 2.5"

        if "over" in low and "1.5" in low:
            return "Over 1.5"
        if "over" in low and "2.5" in low:
            return "Over 2.5"
        if "under" in low and "1.5" in low:
            return "Under 1.5"
        if "under" in low and "2.5" in low:
            return "Under 2.5"

    if market == "Both Teams Score":
        low = v.lower()
        if low in ["yes", "sim", "both", "btts yes"]:
            return "Yes"
        if low in ["no", "nao", "não", "btts no"]:
            return "No"

    return v


def calculate_recent_stats(db: Session, league: int, season: int, max_games: int = 10) -> int:
    teams = db.query(Fixture.home_team_id).filter(Fixture.league_id == league, Fixture.season == season).distinct().all()
    team_ids = [t[0] for t in teams]
    updated = 0
    for team_id in team_ids:
        games = (
            db.query(Fixture)
            .filter(Fixture.league_id == league, Fixture.season == season, Fixture.status == "FT")
            .filter((Fixture.home_team_id == team_id) | (Fixture.away_team_id == team_id))
            .order_by(Fixture.date.desc())
            .limit(max_games)
            .all()
        )
        if not games:
            continue
        gf, ga, btts, over15, over25 = [], [], 0, 0, 0
        for g in games:
            if g.home_goals is None or g.away_goals is None:
                continue
            if g.home_team_id == team_id:
                goals_for, goals_against = g.home_goals, g.away_goals
            else:
                goals_for, goals_against = g.away_goals, g.home_goals
            total = g.home_goals + g.away_goals
            gf.append(goals_for)
            ga.append(goals_against)
            btts += 1 if g.home_goals > 0 and g.away_goals > 0 else 0
            over15 += 1 if total > 1.5 else 0
            over25 += 1 if total > 2.5 else 0
        matches = len(gf)
        if matches == 0:
            continue
        values = {
            "team_id": team_id,
            "league_id": league,
            "season": season,
            "matches": matches,
            "goals_for_avg": sum(gf) / matches,
            "goals_against_avg": sum(ga) / matches,
            "btts_rate": btts / matches,
            "over15_rate": over15 / matches,
            "over25_rate": over25 / matches,
        }
        stmt = sqlite_insert(TeamRecentStat).values(**values)
        stmt = stmt.on_conflict_do_update(index_elements=["team_id", "league_id", "season"], set_=values)
        db.execute(stmt)
        updated += 1
    db.commit()
    return updated
