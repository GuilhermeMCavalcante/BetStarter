from app.db.session import Base, engine
from app.models.entities import Fixture, Odd, Recommendation, RecommendationAudit, TeamRating, TeamRecentStat  # noqa


def init_db():
    Base.metadata.create_all(bind=engine)
