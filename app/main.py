from fastapi import FastAPI, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.config import settings, validate_world_cup_scope
from app.db.session import get_db
from app.db.init_db import init_db
from app.services.collector import fetch_and_store_fixtures, fetch_and_store_odds, calculate_recent_stats
from app.services.recommender import generate_recommendations, list_recommendations

app = FastAPI(title="World Cup Bet Recommender MVP")


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "world_cup_only": settings.world_cup_only,
        "league_id": settings.world_cup_league_id,
        "season": settings.world_cup_season,
    }


@app.post("/collect/fixtures")
def collect_fixtures(
    league: int | None = None,
    season: int | None = None,
    days: int = 3,
    db: Session = Depends(get_db),
):
    try:
        league, season = validate_world_cup_scope(league, season)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    count = fetch_and_store_fixtures(db, league=league, season=season, days=days)
    return {"competition": "FIFA World Cup", "league": league, "season": season, "fixtures_saved": count}


@app.post("/collect/odds")
def collect_odds(
    league: int | None = None,
    season: int | None = None,
    bookmaker: int | None = None,
    db: Session = Depends(get_db),
):
    try:
        league, season = validate_world_cup_scope(league, season)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    count = fetch_and_store_odds(db, league=league, season=season, bookmaker=bookmaker)
    return {"competition": "FIFA World Cup", "league": league, "season": season, "odds_saved": count}


@app.post("/stats/recent")
def recent_stats(
    league: int | None = None,
    season: int | None = None,
    db: Session = Depends(get_db),
):
    try:
        league, season = validate_world_cup_scope(league, season)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    count = calculate_recent_stats(db, league=league, season=season)
    return {"competition": "FIFA World Cup", "league": league, "season": season, "teams_updated": count}


@app.post("/recommendations/generate")
def generate(min_ev: float | None = None, db: Session = Depends(get_db)):
    league, season = validate_world_cup_scope()
    count = generate_recommendations(db, min_ev=min_ev, league=league, season=season)
    return {"competition": "FIFA World Cup", "league": league, "season": season, "recommendations_generated": count}


@app.get("/recommendations")
def recommendations(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    league, season = validate_world_cup_scope()
    rows = list_recommendations(db, limit=limit, league=league, season=season)
    return [
        {
            "fixture_id": r.fixture_id,
            "date": r.date,
            "game": f"{r.home_team} x {r.away_team}",
            "market": r.market,
            "selection": r.selection,
            "bookmaker": r.bookmaker,
            "odd": r.odd,
            "model_probability": r.model_probability,
            "implied_probability": r.implied_probability,
            "edge": r.edge,
            "expected_value": r.expected_value,
            "confidence": r.confidence,
            "suggested_stake_pct": r.suggested_stake_pct,
        }
        for r in rows
    ]
