from __future__ import annotations

import logging
from sqlalchemy import func

from app.config import validate_world_cup_scope
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models.entities import RecommendationAudit
from app.services.collector import fetch_and_store_fixtures, fetch_and_store_odds, calculate_recent_stats
from app.services.recommender import generate_recommendations
from app.services.worldcup_model import seed_team_ratings

log = logging.getLogger(__name__)


def run_pipeline(days: int = 7, past_days: int = 10) -> dict:
    """Collect fixtures and odds, compute stats, and generate recommendations."""
    init_db()
    league, season = validate_world_cup_scope()

    with SessionLocal() as db:
        ratings = seed_team_ratings(db)
        fixtures = fetch_and_store_fixtures(db, league, season, days=days, past_days=past_days)
        odds = fetch_and_store_odds(db, league, season)
        stats = calculate_recent_stats(db, league, season)
        recs = generate_recommendations(
            db, league=league, season=season, days=days, past_days=past_days
        )
        analyzed = (
            db.query(func.count(RecommendationAudit.id))
            .filter(
                RecommendationAudit.league_id == league,
                RecommendationAudit.season == season,
            )
            .scalar() or 0
        )

    log.info("Pipeline complete: fixtures=%d odds=%d recs=%d", fixtures, odds, recs)
    return {
        "league": league,
        "season": season,
        "fixtures": fixtures,
        "odds": odds,
        "ratings_seeded": ratings,
        "stats_updated": stats,
        "odds_analyzed": analyzed,
        "recommendations": recs,
    }
