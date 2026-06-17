from __future__ import annotations

from dataclasses import dataclass
from math import exp, factorial
from typing import Iterable

from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.models.entities import Fixture, Odd, TeamRating, TeamRecentStat
from datetime import datetime

# Manual prior ratings on a 50–100 scale. Used before sufficient in-tournament statistics accumulate.
DEFAULT_TEAM_RATINGS = {
    "Argentina": 92, "France": 91, "Brazil": 90, "Spain": 89, "England": 88,
    "Portugal": 87, "Germany": 86, "Netherlands": 85, "Belgium": 84, "Uruguay": 83,
    "Croatia": 82, "Colombia": 81, "Morocco": 80, "Switzerland": 79, "United States": 78,
    "Mexico": 78, "Japan": 77, "Senegal": 77, "Ecuador": 76, "Austria": 76,
    "Turkey": 75, "Australia": 74, "Iran": 74, "South Korea": 74, "Canada": 73,
    "Scotland": 73, "Egypt": 73, "Czechia": 72, "Norway": 72, "Sweden": 72,
    "Paraguay": 71, "Ghana": 71, "Ivory Coast": 71, "Algeria": 70, "Saudi Arabia": 69,
    "Qatar": 68, "South Africa": 68, "Tunisia": 68, "Bosnia and Herzegovina": 68,
    "Panama": 66, "New Zealand": 65, "Uzbekistan": 65, "DR Congo": 65,
    "Iraq": 64, "Jordan": 63, "Cape Verde": 63, "Haiti": 62, "Curacao": 60,
}

ALIASES = {
    "Côte d'Ivoire": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "Türkiye": "Turkey",
    "USA": "United States",
    "Korea Republic": "South Korea",
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Czech Republic": "Czechia",
    "Congo DR": "DR Congo",
}

@dataclass
class ModelOutput:
    probability: float
    expected_home_goals: float
    expected_away_goals: float
    confidence_score: int
    reason: str


def clamp(value: float, low: float = 0.01, high: float = 0.95) -> float:
    return max(low, min(high, value))


def canonical_team_name(name: str | None) -> str:
    if not name:
        return ""
    return ALIASES.get(name, name)


def seed_team_ratings(db: Session) -> int:
    count = 0
    now = datetime.utcnow()
    for team_name, rating in DEFAULT_TEAM_RATINGS.items():
        values = {"team_name": team_name, "rating": float(rating), "source": "manual_v1", "updated_at": now}
        stmt = sqlite_insert(TeamRating).values(**values)
        stmt = stmt.on_conflict_do_update(index_elements=["team_name"], set_=values)
        db.execute(stmt)
        count += 1
    db.commit()
    return count


def get_rating(db: Session, team_name: str) -> float:
    canonical = canonical_team_name(team_name)
    row = db.query(TeamRating).filter(TeamRating.team_name == canonical).first()
    if row:
        return float(row.rating)
    return float(DEFAULT_TEAM_RATINGS.get(canonical, 70.0))


def poisson_pmf(k: int, lam: float) -> float:
    return exp(-lam) * (lam ** k) / factorial(k)


def poisson_over_probability(total_lambda: float, line: float) -> float:
    if line == 1.5:
        return 1 - sum(poisson_pmf(k, total_lambda) for k in range(0, 2))
    if line == 2.5:
        return 1 - sum(poisson_pmf(k, total_lambda) for k in range(0, 3))
    raise ValueError(f"Unsupported over line: {line}")

def poisson_under_probability(total_lambda: float, line: float) -> float:
    if line == 3.5:
        return sum(poisson_pmf(k, total_lambda) for k in range(0, 4))
    raise ValueError(f"Unsupported under line: {line}")

def btts_probability(home_lambda: float, away_lambda: float) -> float:
    return (1 - exp(-home_lambda)) * (1 - exp(-away_lambda))


def no_vig_probability(odds: Iterable[Odd], selection: str) -> float | None:
    same_market = list(odds)
    implied = []
    selected = None
    for odd in same_market:
        if odd.odd <= 1:
            continue
        p = 1 / odd.odd
        implied.append(p)
        if odd.selection == selection:
            selected = p
    total = sum(implied)
    if not selected or total <= 0:
        return None
    return selected / total


def estimate_expected_goals(
    db: Session,
    fixture: Fixture,
    home_stats: TeamRecentStat | None,
    away_stats: TeamRecentStat | None,
) -> tuple[float, float, str, int]:
    home_rating = get_rating(db, fixture.home_team)
    away_rating = get_rating(db, fixture.away_team)
    diff = home_rating - away_rating

    # Tournament baseline is lower-scoring than domestic leagues.
    base_home = 1.22
    base_away = 1.05

    home_lambda = base_home + clamp(diff / 35.0, -0.45, 0.65)
    away_lambda = base_away - clamp(diff / 42.0, -0.55, 0.45)

    reason_bits = [f"rating {fixture.home_team}={home_rating:.0f}, {fixture.away_team}={away_rating:.0f}"]
    confidence = 58

    if home_stats and away_stats and home_stats.matches > 0 and away_stats.matches > 0:
        stat_home = (home_stats.goals_for_avg + away_stats.goals_against_avg) / 2
        stat_away = (away_stats.goals_for_avg + home_stats.goals_against_avg) / 2
        weight = min(0.45, 0.12 + 0.04 * min(home_stats.matches, away_stats.matches))
        home_lambda = (home_lambda * (1 - weight)) + (stat_home * weight)
        away_lambda = (away_lambda * (1 - weight)) + (stat_away * weight)
        confidence += min(18, min(home_stats.matches, away_stats.matches) * 3)
        reason_bits.append(f"recent stats used ({min(home_stats.matches, away_stats.matches)} matches)")
    else:
        reason_bits.append("no sufficient stats; using rating prior only")

    return clamp(home_lambda, 0.2, 3.4), clamp(away_lambda, 0.15, 3.0), "; ".join(reason_bits), confidence


def calculate_market_probability(
    db: Session,
    fixture: Fixture,
    home_stats: TeamRecentStat | None,
    away_stats: TeamRecentStat | None,
    market: str,
    selection: str,
) -> ModelOutput:
    home_lam, away_lam, reason, confidence = estimate_expected_goals(db, fixture, home_stats, away_stats)
    total_lam = home_lam + away_lam

    trend = None
    if home_stats and away_stats and home_stats.matches > 0 and away_stats.matches > 0:
        if market == "Over/Under" and selection == "Over 1.5":
            trend = (home_stats.over15_rate + away_stats.over15_rate) / 2
        elif market == "Over/Under" and selection == "Over 2.5":
            trend = (home_stats.over25_rate + away_stats.over25_rate) / 2
        elif market == "Over/Under" and selection == "Under 3.5":
            home_under35 = 1 - home_stats.over25_rate
            away_under35 = 1 - away_stats.over25_rate
            trend = (home_under35 + away_under35) / 2
        elif market == "Both Teams Score" and selection == "Yes":
            trend = (home_stats.btts_rate + away_stats.btts_rate) / 2
        elif market == "Both Teams Score" and selection == "No":
            trend = 1 - ((home_stats.btts_rate + away_stats.btts_rate) / 2)

    if market == "Over/Under" and selection == "Over 1.5":
        poisson_prob = poisson_over_probability(total_lam, 1.5)
    elif market == "Over/Under" and selection == "Over 2.5":
        poisson_prob = poisson_over_probability(total_lam, 2.5)
    elif market == "Both Teams Score" and selection == "Yes":
        poisson_prob = btts_probability(home_lam, away_lam)
    elif market == "Over/Under" and selection == "Under 3.5":
        poisson_prob = poisson_under_probability(total_lam, 3.5)
    elif market == "Both Teams Score" and selection == "No":
        poisson_prob = 1 - btts_probability(home_lam, away_lam)
    else:
        return ModelOutput(0.0, home_lam, away_lam, 0, "unsupported market")

    if trend is not None:
        probability = (poisson_prob * 0.72) + (trend * 0.28)
        reason += f"; poisson={poisson_prob:.1%}; trend={trend:.1%}"
    else:
        probability = poisson_prob
        reason += f"; poisson={poisson_prob:.1%}"

    # Conservative shrinkage to dampen model overconfidence in early-tournament samples.
    probability = (probability * 0.96) + 0.02
    return ModelOutput(clamp(probability), home_lam, away_lam, min(confidence, 92), reason)
