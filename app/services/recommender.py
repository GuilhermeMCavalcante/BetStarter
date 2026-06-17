from __future__ import annotations

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from zoneinfo import ZoneInfo
from app.config import settings
from app.models.entities import Fixture, Odd, Recommendation, RecommendationAudit, TeamRecentStat
from app.services.worldcup_model import calculate_market_probability, seed_team_ratings

SUPPORTED_RECOMMENDATION_SELECTIONS = {
    ("Over/Under", "Over 0.5"),
    ("Over/Under", "Over 1.5"),
    ("Over/Under", "Over 2.5"),
    ("Over/Under", "Over 3.5"),
    ("Over/Under", "Under 3.5"),
    ("Both Teams Score", "Yes"),
    ("Both Teams Score", "No"),
}
BR_TZ = ZoneInfo("America/Sao_Paulo")

def kelly_fraction(probability: float, odd: float) -> float:
    b = odd - 1
    q = 1 - probability
    fraction = ((b * probability) - q) / b if b > 0 else 0
    return round(max(0.0, min(fraction * 0.25, 0.02)), 4)


def confidence_label(confidence_score: int, edge: float) -> str:
    if confidence_score >= 82 and edge >= 0.10:
        return "A"
    if confidence_score >= 72 and edge >= 0.07:
        return "B"
    if confidence_score >= 62 and edge >= 0.05:
        return "C"
    return "Baixa"


def audit(
    db: Session,
    fixture: Fixture,
    odd: Odd,
    probability: float,
    implied: float,
    edge: float,
    ev: float,
    status: str,
    reason: str,
) -> None:
    db.add(RecommendationAudit(
        fixture_id=fixture.id,
        league_id=fixture.league_id,
        season=fixture.season,
        date=fixture.date,
        home_team=fixture.home_team,
        away_team=fixture.away_team,
        market=odd.market,
        selection=odd.selection,
        bookmaker=odd.bookmaker,
        odd=odd.odd,
        model_probability=round(probability, 4),
        implied_probability=round(implied, 4),
        edge=round(edge, 4),
        expected_value=round(ev, 4),
        status=status,
        reason=reason[:500],
        created_at=datetime.utcnow(),
    ))


def generate_recommendations(db: Session, min_ev: float | None = None, league: int | None = None, season: int | None = None, days: int = 3, past_days: int = 0) -> int:
    min_ev = settings.min_ev if min_ev is None else min_ev
    seed_team_ratings(db)
    #today_start = datetime.combine(datetime.now().date(), time.min)
    today_start = (datetime.now(BR_TZ).date() - timedelta(days=past_days)).isoformat()
    date_to = (datetime.now(BR_TZ).date() + timedelta(days=days)).isoformat()
    fixture_query = db.query(Fixture).filter(
        Fixture.date >= today_start,
        #Fixture.status.in_(["NS", "TBD"])
    )
    if league is not None:
        fixture_query = fixture_query.filter(Fixture.league_id == league)
    if season is not None:
        fixture_query = fixture_query.filter(Fixture.season == season)
    fixtures = fixture_query.order_by(Fixture.date.asc()).all()

    if league is not None and season is not None:
        db.query(RecommendationAudit).filter(
            RecommendationAudit.league_id == league,
            RecommendationAudit.season == season,
        ).delete(synchronize_session=False)
        # Limpa recomendacoes antigas da competicao para o dashboard refletir somente o modelo atual.
        old_rec_query = db.query(Recommendation).filter(Recommendation.league_id == league)
        old_rec_query.delete(synchronize_session=False)
        db.commit()

    created = 0
    for fixture in fixtures:
        home_stats = db.query(TeamRecentStat).filter_by(
            team_id=fixture.home_team_id, league_id=fixture.league_id, season=fixture.season
        ).first()
        away_stats = db.query(TeamRecentStat).filter_by(
            team_id=fixture.away_team_id, league_id=fixture.league_id, season=fixture.season
        ).first()

        odds = db.query(Odd).filter(Odd.fixture_id == fixture.api_fixture_id).all()

        if not odds:
            odds = db.query(Odd).filter(
                Odd.fixture_id.in_(
                    db.query(Odd.fixture_id)
                    .filter(Odd.fixture_id != fixture.id)
                    .distinct()
                )
            ).limit(300).all()

        for odd in odds:
            if odd.bookmaker.lower() != "superbet":
                continue
            if (odd.market, odd.selection) not in SUPPORTED_RECOMMENDATION_SELECTIONS:
                continue
            if odd.odd <= 1:
                continue

            output = calculate_market_probability(db, fixture, home_stats, away_stats, odd.market, odd.selection)
            probability = output.probability
            if probability <= 0:
                audit(db, fixture, odd, 0, 0, 0, 0, "REJECTED", "mercado nao suportado")
                continue

            implied = 1 / odd.odd
            edge = probability - implied
            ev = (probability * odd.odd) - 1

            if output.confidence_score < 55:
                audit(db, fixture, odd, probability, implied, edge, ev, "REJECTED",
                      f"Confianca baixa ({output.confidence_score}). {output.reason}")
                continue

            if odd.market == "Both Teams Score":
                if odd.selection == "Yes":
                    if edge < 0.08 or ev < 0.15:
                        audit(db, fixture, odd, probability, implied, edge, ev, "REJECTED",
                              f"BTTS Yes sem valor suficiente. Edge {edge:.2%}, EV {ev:.2%}. {output.reason}")
                        continue

                if odd.selection == "No":
                    if probability < 0.52:
                        audit(db, fixture, odd, probability, implied, edge, ev, "REJECTED",
                              f"BTTS No com probabilidade baixa ({probability:.2%}). {output.reason}")
                        continue

                    if edge < 0.05 or ev < 0.08:
                        audit(db, fixture, odd, probability, implied, edge, ev, "REJECTED",
                              f"BTTS No sem valor suficiente. Edge {edge:.2%}, EV {ev:.2%}. {output.reason}")
                        continue

            if odd.market == "Over/Under":
                if odd.selection == "Under 3.5" and probability < 0.68:
                    audit(db, fixture, odd, probability, implied, edge, ev, "REJECTED",
                          f"Under 3.5 com probabilidade baixa ({probability:.2%}). {output.reason}")
                    continue
                if odd.selection == "Over 2.5" and probability < 0.42:
                    audit(db, fixture, odd, probability, implied, edge, ev, "REJECTED",
                          f"Over 2.5 com probabilidade baixa ({probability:.2%}). {output.reason}")
                    continue

                if odd.selection == "Over 1.5" and probability < 0.62:
                    audit(db, fixture, odd, probability, implied, edge, ev, "REJECTED",
                          f"Over 1.5 com probabilidade baixa ({probability:.2%}). {output.reason}")
                    continue

                if edge < 0.05 or ev < 0.08:
                    audit(db, fixture, odd, probability, implied, edge, ev, "REJECTED",
                          f"Over/Under sem valor suficiente. Edge {edge:.2%}, EV {ev:.2%}. {output.reason}")
                    continue

            values = {
                "fixture_id": fixture.id,
                "league_id": fixture.league_id,
                "date": fixture.date,
                "home_team": fixture.home_team,
                "away_team": fixture.away_team,
                "market": odd.market,
                "selection": odd.selection,
                "bookmaker": odd.bookmaker,
                "odd": odd.odd,
                "model_probability": round(probability, 4),
                "implied_probability": round(implied, 4),
                "edge": round(edge, 4),
                "expected_value": round(ev, 4),
                "confidence": confidence_label(output.confidence_score, edge),
                "suggested_stake_pct": kelly_fraction(probability, odd.odd),
                "created_at": datetime.utcnow(),
            }
            stmt = sqlite_insert(Recommendation).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["fixture_id", "market", "selection", "bookmaker"],
                set_=values,
            )
            db.execute(stmt)
            audit(db, fixture, odd, probability, implied, edge, ev, "APPROVED", output.reason)
            created += 1

    db.commit()
    return created


def list_recommendations(db: Session, limit: int = 50, league: int | None = None, season: int | None = None):
    query = db.query(Recommendation)
    if league is not None:
        query = query.filter(Recommendation.league_id == league)
    if season is not None:
        query = query.join(Fixture, Fixture.id == Recommendation.fixture_id).filter(Fixture.season == season)
    return query.order_by(Recommendation.expected_value.desc(), Recommendation.date.asc()).limit(limit).all()


def list_audits(db: Session, limit: int = 100, league: int | None = None, season: int | None = None, status: str | None = None):
    query = db.query(RecommendationAudit)
    if league is not None:
        query = query.filter(RecommendationAudit.league_id == league)
    if season is not None:
        query = query.filter(RecommendationAudit.season == season)
    return query.order_by(RecommendationAudit.created_at.desc()).limit(limit).all()
