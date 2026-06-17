import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
from sqlalchemy import func
from app.config import validate_world_cup_scope
from app.db.session import SessionLocal
from app.db.init_db import init_db
from app.models.entities import RecommendationAudit
from app.services.collector import fetch_and_store_fixtures, fetch_and_store_odds, calculate_recent_stats
from app.services.recommender import generate_recommendations
from app.services.worldcup_model import seed_team_ratings

parser = argparse.ArgumentParser(description="Pipeline travado para Copa do Mundo por padrao.")
parser.add_argument("--league", type=int, default=None)
parser.add_argument("--season", type=int, default=None)
parser.add_argument("--days", type=int, default=7)
parser.add_argument("--bookmaker", type=int, default=None)
parser.add_argument("--past-days", type=int, default=10)
args = parser.parse_args()

league, season = validate_world_cup_scope(args.league, args.season)

init_db()
db = SessionLocal()
try:
    ratings = seed_team_ratings(db)
    fixtures = fetch_and_store_fixtures(
        db,
        league,
        season,
        days=args.days,
        past_days=args.past_days,
    )
    odds = fetch_and_store_odds(db, league, season, args.bookmaker)
    stats = calculate_recent_stats(db, league, season)
    recs = generate_recommendations(db, league=league, season=season,days=args.days,past_days=args.past_days)
    analyzed = db.query(func.count(RecommendationAudit.id)).filter(
        RecommendationAudit.league_id == league,
        RecommendationAudit.season == season,
    ).scalar() or 0
    print({
        "competition": "FIFA World Cup",
        "league": league,
        "season": season,
        "fixtures": fixtures,
        "odds": odds,
        "ratings_seeded": ratings,
        "stats": stats,
        "odds_analyzed": analyzed,
        "recommendations": recs,
    })
finally:
    db.close()
