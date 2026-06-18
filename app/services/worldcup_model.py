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


def _set_rating(db: Session, team_name: str, new_rating: float) -> None:
    canonical = canonical_team_name(team_name)
    row = db.query(TeamRating).filter(TeamRating.team_name == canonical).first()
    clamped = round(max(40.0, min(100.0, new_rating)), 2)
    if row:
        row.rating = clamped
        row.source = "elo_auto"
        row.updated_at = datetime.utcnow()
    else:
        db.add(TeamRating(team_name=canonical, rating=clamped, source="elo_auto", updated_at=datetime.utcnow()))


def elo_update_ratings(db: Session, league: int, season: int, k_factor: float = 6.0) -> int:
    """Apply Elo-style rating updates from completed fixture results.

    Each completed match adjusts both teams' ratings proportional to how surprising
    the result was relative to the current rating gap. The more matches complete,
    the more the ratings reflect actual tournament performance instead of manual priors.
    """
    fixtures = (
        db.query(Fixture)
        .filter(
            Fixture.league_id == league,
            Fixture.season == season,
            Fixture.status.in_(["FT", "AET", "PEN"]),
            Fixture.home_goals.isnot(None),
            Fixture.away_goals.isnot(None),
        )
        .order_by(Fixture.date.asc())
        .all()
    )

    # Reset to manual priors before replaying all results so updates are idempotent.
    seed_team_ratings(db)

    updated = 0
    for f in fixtures:
        home_r = get_rating(db, f.home_team)
        away_r = get_rating(db, f.away_team)

        expected_home = 1 / (1 + 10 ** ((away_r - home_r) / 400))

        if f.home_goals > f.away_goals:
            actual_home = 1.0
        elif f.home_goals == f.away_goals:
            actual_home = 0.5
        else:
            actual_home = 0.0

        delta = k_factor * (actual_home - expected_home)
        _set_rating(db, f.home_team, home_r + delta)
        _set_rating(db, f.away_team, away_r - delta)
        updated += 1

    db.commit()
    return updated


def poisson_pmf(k: int, lam: float) -> float:
    return exp(-lam) * (lam ** k) / factorial(k)


def poisson_over_probability(total_lambda: float, line: float) -> float:
    k_max = int(line + 0.5)  # number of goals that would be "under"
    return 1 - sum(poisson_pmf(k, total_lambda) for k in range(0, k_max + 1))

def poisson_under_probability(total_lambda: float, line: float) -> float:
    k_max = int(line + 0.5)  # last integer below the line
    return sum(poisson_pmf(k, total_lambda) for k in range(0, k_max + 1))

def btts_probability(home_lambda: float, away_lambda: float) -> float:
    return (1 - exp(-home_lambda)) * (1 - exp(-away_lambda))


def calculate_1x2(
    db: Session,
    fixture,
    home_stats,
    away_stats,
    max_goals: int = 9,
) -> dict:
    """Return Home/Draw/Away win probabilities via Poisson score matrix."""
    home_lam, away_lam, reason, confidence = estimate_expected_goals(db, fixture, home_stats, away_stats)

    p_home = p_draw = p_away = 0.0
    most_likely_score = (0, 0)
    best_score_prob = 0.0

    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = poisson_pmf(h, home_lam) * poisson_pmf(a, away_lam)
            if p > best_score_prob:
                best_score_prob = p
                most_likely_score = (h, a)
            if h > a:
                p_home += p
            elif h == a:
                p_draw += p
            else:
                p_away += p

    # Normalise rounding residue
    total = p_home + p_draw + p_away
    if total > 0:
        p_home /= total
        p_draw /= total
        p_away /= total

    outcomes = {"1": p_home, "X": p_draw, "2": p_away}
    tip = max(outcomes, key=outcomes.get)

    return {
        "home": round(p_home, 4),
        "draw": round(p_draw, 4),
        "away": round(p_away, 4),
        "tip": tip,
        "expected_home_goals": round(home_lam, 2),
        "expected_away_goals": round(away_lam, 2),
        "most_likely_score": most_likely_score,
        "most_likely_score_prob": round(best_score_prob, 4),
        "confidence": confidence,
        "reason": reason,
    }


# ── Corners model ──────────────────────────────────────────────────────────────

# World Cup baseline: ~10 total corners per match (home ~5.5, away ~4.5)
BASE_CORNERS_HOME = 5.5
BASE_CORNERS_AWAY = 4.5


def estimate_expected_corners(
    home_stats: TeamRecentStat | None,
    away_stats: TeamRecentStat | None,
) -> tuple[float, float, str, int]:
    home_lam = BASE_CORNERS_HOME
    away_lam = BASE_CORNERS_AWAY
    confidence = 50
    reason_bits = ["corner prior: base 5.5/4.5"]

    if (home_stats and away_stats
            and home_stats.corners_for_avg is not None
            and home_stats.corners_against_avg is not None
            and away_stats.corners_for_avg is not None
            and away_stats.corners_against_avg is not None):
        stat_home = (home_stats.corners_for_avg + away_stats.corners_against_avg) / 2
        stat_away = (away_stats.corners_for_avg + home_stats.corners_against_avg) / 2
        n = min(home_stats.matches, away_stats.matches)
        weight = min(0.55, 0.15 + 0.04 * n)
        home_lam = home_lam * (1 - weight) + stat_home * weight
        away_lam = away_lam * (1 - weight) + stat_away * weight
        confidence += min(25, n * 4)
        reason_bits.append(f"corner stats used ({n} matches, weight={weight:.0%})")
    else:
        reason_bits.append("no corner stats; using prior only")

    return (
        clamp(home_lam, 1.0, 12.0),
        clamp(away_lam, 1.0, 10.0),
        "; ".join(reason_bits),
        min(confidence, 88),
    )


def calculate_corners_probability(
    home_stats: TeamRecentStat | None,
    away_stats: TeamRecentStat | None,
    selection: str,
) -> ModelOutput:
    home_lam, away_lam, reason, confidence = estimate_expected_corners(home_stats, away_stats)
    total_lam = home_lam + away_lam

    corner_lines = {
        "Over 8.5": 8.5,
        "Over 9.5": 9.5,
        "Over 10.5": 10.5,
        "Over 11.5": 11.5,
        "Under 8.5": 8.5,
        "Under 9.5": 9.5,
        "Under 10.5": 10.5,
    }

    if selection not in corner_lines:
        return ModelOutput(0.0, home_lam, away_lam, 0, "unsupported corner selection")

    line = corner_lines[selection]
    if selection.startswith("Over"):
        poisson_prob = 1 - poisson_under_probability(total_lam, line - 0.5)
    else:
        poisson_prob = poisson_under_probability(total_lam, line - 0.5)

    # Blend with historical rate when available
    trend = None
    if home_stats and away_stats:
        if selection == "Over 9.5" and home_stats.over95_corners_rate is not None:
            trend = (home_stats.over95_corners_rate + away_stats.over95_corners_rate) / 2
        elif selection == "Over 10.5" and home_stats.over105_corners_rate is not None:
            trend = (home_stats.over105_corners_rate + away_stats.over105_corners_rate) / 2

    if trend is not None:
        probability = poisson_prob * 0.65 + trend * 0.35
        reason += f"; poisson={poisson_prob:.1%}; trend={trend:.1%}"
    else:
        probability = poisson_prob
        reason += f"; poisson={poisson_prob:.1%}"

    probability = (probability * 0.96) + 0.02
    return ModelOutput(clamp(probability), home_lam, away_lam, confidence, reason)


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
