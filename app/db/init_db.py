from sqlalchemy import text

from app.db.session import Base, engine
from app.models.entities import (  # noqa — imports register models with Base.metadata
    BacktestResult,
    Fixture,
    HistoricalTeamStat,
    Odd,
    Recommendation,
    RecommendationAudit,
    TeamRating,
    TeamRecentStat,
    TelegramSignal,
)


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate()


def _migrate():
    """Add new columns to existing tables without dropping data."""
    migrations = [
        "ALTER TABLE fixtures ADD COLUMN home_corners INTEGER",
        "ALTER TABLE fixtures ADD COLUMN away_corners INTEGER",
        "ALTER TABLE team_recent_stats ADD COLUMN corners_for_avg REAL",
        "ALTER TABLE team_recent_stats ADD COLUMN corners_against_avg REAL",
        "ALTER TABLE team_recent_stats ADD COLUMN over95_corners_rate REAL",
        "ALTER TABLE team_recent_stats ADD COLUMN over105_corners_rate REAL",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                pass  # column already exists
