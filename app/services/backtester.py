from __future__ import annotations

import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.config import settings
from app.models.entities import Fixture, Odd, TeamRecentStat, BacktestResult
from app.services.worldcup_model import calculate_market_probability, seed_team_ratings

log = logging.getLogger(__name__)

SUPPORTED_BACKTEST_SELECTIONS = {
    ("Over/Under", "Over 1.5"),
    ("Over/Under", "Over 2.5"),
    ("Both Teams Score", "Yes"),
}


def bet_won(market: str, selection: str, home_goals: int, away_goals: int) -> bool:
    total = home_goals + away_goals
    if market == "Over/Under":
        lines = {"Over 0.5": 0.5, "Over 1.5": 1.5, "Over 2.5": 2.5, "Over 3.5": 3.5}
        if selection in lines:
            return total > lines[selection]
        if selection == "Under 3.5":
            return total < 3.5
    if market == "Both Teams Score":
        btts = home_goals > 0 and away_goals > 0
        if selection == "Yes":
            return btts
        if selection == "No":
            return not btts
    return False


def run_backtest(
    db: Session,
    league: int,
    season: int,
    bookmaker: str = "Superbet",
    min_ev: float | None = None,
    stake: float = 1.0,
) -> dict:
    min_ev = settings.min_ev if min_ev is None else min_ev
    seed_team_ratings(db)

    db.query(BacktestResult).filter(
        BacktestResult.league_id == league,
        BacktestResult.season == season,
    ).delete(synchronize_session=False)
    db.commit()

    fixtures = db.query(Fixture).filter(
        Fixture.league_id == league,
        Fixture.season == season,
        Fixture.status.in_(["FT", "AET", "PEN"]),
        Fixture.home_goals.isnot(None),
        Fixture.away_goals.isnot(None),
    ).order_by(Fixture.date.asc()).all()

    analyzed = 0
    entries = 0
    wins = 0
    profit_total = 0.0

    for fixture in fixtures:
        home_stats = build_team_stats_before_fixture(
            db=db,
            team_id=fixture.home_team_id,
            league=fixture.league_id,
            season=fixture.season,
            before_date=fixture.date,
        )
        away_stats = build_team_stats_before_fixture(
            db=db,
            team_id=fixture.away_team_id,
            league=fixture.league_id,
            season=fixture.season,
            before_date=fixture.date,
        )

        odds = db.query(Odd).filter(
            Odd.fixture_id == fixture.api_fixture_id,
            Odd.bookmaker == bookmaker,
        ).all()

        for odd in odds:
            if (odd.market, odd.selection) not in SUPPORTED_BACKTEST_SELECTIONS:
                continue
            if odd.odd <= 1:
                continue

            analyzed += 1

            output = calculate_market_probability(
                db, fixture, home_stats, away_stats, odd.market, odd.selection,
            )
            probability = output.probability
            if probability <= 0:
                continue

            implied = 1 / odd.odd
            edge = probability - implied
            ev = (probability * odd.odd) - 1

            if output.confidence_score < 55:
                log.debug("Rejected (low confidence %d): %s %s %s", output.confidence_score, fixture.home_team, odd.market, odd.selection)
                continue

            if odd.market == "Both Teams Score":
                if edge < 0.08 or ev < 0.15:
                    log.debug("Rejected BTTS (edge=%.3f ev=%.3f): %s", edge, ev, fixture.home_team)
                    continue

            if odd.market == "Over/Under":
                if odd.selection == "Over 2.5" and probability < 0.42:
                    log.debug("Rejected Over 2.5 low prob=%.3f: %s", probability, fixture.home_team)
                    continue
                if odd.selection == "Over 1.5" and probability < 0.42:
                    log.debug("Rejected Over 1.5 low prob=%.3f: %s", probability, fixture.home_team)
                    continue
                if edge < 0.05 or ev < 0.08:
                    log.debug("Rejected Over/Under (edge=%.3f ev=%.3f): %s", edge, ev, fixture.home_team)
                    continue

            won = bet_won(odd.market, odd.selection, fixture.home_goals, fixture.away_goals)
            result = "WIN" if won else "LOSS"
            profit = (odd.odd - 1) * stake if won else -stake

            values = {
                "fixture_id": fixture.api_fixture_id,
                "league_id": fixture.league_id,
                "season": fixture.season,
                "date": fixture.date,
                "home_team": fixture.home_team,
                "away_team": fixture.away_team,
                "home_goals": fixture.home_goals,
                "away_goals": fixture.away_goals,
                "market": odd.market,
                "selection": odd.selection,
                "bookmaker": odd.bookmaker,
                "odd": odd.odd,
                "model_probability": round(probability, 4),
                "implied_probability": round(implied, 4),
                "edge": round(edge, 4),
                "expected_value": round(ev, 4),
                "stake": stake,
                "result": result,
                "profit": round(profit, 4),
                "created_at": datetime.utcnow(),
            }

            stmt = sqlite_insert(BacktestResult).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["fixture_id", "market", "selection", "bookmaker"],
                set_=values,
            )
            db.execute(stmt)

            entries += 1
            wins += 1 if won else 0
            profit_total += profit

    db.commit()
    roi = profit_total / (entries * stake) if entries else 0

    log.info("Backtest complete: %d fixtures, %d entries, %d wins, profit=%.2f, roi=%.1f%%", len(fixtures), entries, wins, profit_total, roi * 100)
    return {
        "fixtures": len(fixtures),
        "odds_analyzed": analyzed,
        "entries": entries,
        "wins": wins,
        "losses": entries - wins,
        "hit_rate": round(wins / entries, 4) if entries else 0,
        "profit": round(profit_total, 4),
        "roi": round(roi, 4),
    }


def list_backtest_results(db: Session, league: int, season: int, limit: int = 200):
    return (
        db.query(BacktestResult)
        .filter(BacktestResult.league_id == league, BacktestResult.season == season)
        .order_by(BacktestResult.date.desc())
        .limit(limit)
        .all()
    )


def build_team_stats_before_fixture(db, team_id, league, season, before_date, max_games=10):
    games = (
        db.query(Fixture)
        .filter(
            Fixture.league_id == league,
            Fixture.season == season,
            Fixture.status.in_(["FT", "AET", "PEN"]),
            Fixture.date < before_date,
        )
        .filter((Fixture.home_team_id == team_id) | (Fixture.away_team_id == team_id))
        .order_by(Fixture.date.desc())
        .limit(max_games)
        .all()
    )

    if not games:
        return None

    gf, ga, btts, over15, over25 = [], [], 0, 0, 0

    for g in games:
        if g.home_goals is None or g.away_goals is None:
            continue
        goals_for = g.home_goals if g.home_team_id == team_id else g.away_goals
        goals_against = g.away_goals if g.home_team_id == team_id else g.home_goals
        total = g.home_goals + g.away_goals
        gf.append(goals_for)
        ga.append(goals_against)
        btts += 1 if g.home_goals > 0 and g.away_goals > 0 else 0
        over15 += 1 if total > 1.5 else 0
        over25 += 1 if total > 2.5 else 0

    matches = len(gf)
    if matches == 0:
        return None

    class Stats:
        pass

    stats = Stats()
    stats.matches = matches
    stats.goals_for_avg = sum(gf) / matches
    stats.goals_against_avg = sum(ga) / matches
    stats.btts_rate = btts / matches
    stats.over15_rate = over15 / matches
    stats.over25_rate = over25 / matches

    return stats
