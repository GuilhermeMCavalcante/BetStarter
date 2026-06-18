from sqlalchemy import Column, Integer, String, Float, DateTime, UniqueConstraint
from app.db.session import Base


class Fixture(Base):
    __tablename__ = "fixtures"

    id = Column(Integer, primary_key=True, index=True)
    api_fixture_id = Column(Integer, unique=True, index=True)
    league_id = Column(Integer, index=True)
    season = Column(Integer, index=True)
    date = Column(DateTime, index=True)
    status = Column(String, default="NS")
    home_team_id = Column(Integer, index=True)
    away_team_id = Column(Integer, index=True)
    home_team = Column(String)
    away_team = Column(String)
    home_goals = Column(Integer, nullable=True)
    away_goals = Column(Integer, nullable=True)
    home_corners = Column(Integer, nullable=True)
    away_corners = Column(Integer, nullable=True)


class Odd(Base):
    __tablename__ = "odds"

    id = Column(Integer, primary_key=True)
    fixture_id = Column(Integer, index=True)
    bookmaker = Column(String, index=True)
    market = Column(String, index=True)
    selection = Column(String, index=True)
    odd = Column(Float)
    updated_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("fixture_id", "bookmaker", "market", "selection", name="uq_odd"),
    )


class TeamRecentStat(Base):
    __tablename__ = "team_recent_stats"

    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, index=True)
    league_id = Column(Integer, index=True)
    season = Column(Integer, index=True)
    matches = Column(Integer, default=0)
    goals_for_avg = Column(Float, default=0)
    goals_against_avg = Column(Float, default=0)
    btts_rate = Column(Float, default=0)
    over15_rate = Column(Float, default=0)
    over25_rate = Column(Float, default=0)
    corners_for_avg = Column(Float, nullable=True)
    corners_against_avg = Column(Float, nullable=True)
    over95_corners_rate = Column(Float, nullable=True)
    over105_corners_rate = Column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("team_id", "league_id", "season", name="uq_team_stats"),
    )


class TeamRating(Base):
    __tablename__ = "team_ratings"

    id = Column(Integer, primary_key=True)
    team_name = Column(String, index=True)
    rating = Column(Float, default=72.0)
    source = Column(String, default="manual")
    updated_at = Column(DateTime)

    __table_args__ = (
        UniqueConstraint("team_name", name="uq_team_rating_name"),
    )


class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True)
    fixture_id = Column(Integer, index=True)
    league_id = Column(Integer, index=True)
    date = Column(DateTime, index=True)
    home_team = Column(String)
    away_team = Column(String)
    market = Column(String, index=True)
    selection = Column(String)
    bookmaker = Column(String)
    odd = Column(Float)
    model_probability = Column(Float)
    implied_probability = Column(Float)
    edge = Column(Float)
    expected_value = Column(Float)
    confidence = Column(String)
    suggested_stake_pct = Column(Float)
    created_at = Column(DateTime)

    __table_args__ = (
        UniqueConstraint("fixture_id", "market", "selection", "bookmaker", name="uq_rec"),
    )


class RecommendationAudit(Base):
    __tablename__ = "recommendation_audits"

    id = Column(Integer, primary_key=True)
    fixture_id = Column(Integer, index=True)
    league_id = Column(Integer, index=True)
    season = Column(Integer, index=True)
    date = Column(DateTime, index=True)
    home_team = Column(String)
    away_team = Column(String)
    market = Column(String, index=True)
    selection = Column(String)
    bookmaker = Column(String)
    odd = Column(Float)
    model_probability = Column(Float)
    implied_probability = Column(Float)
    edge = Column(Float)
    expected_value = Column(Float)
    status = Column(String, index=True)
    reason = Column(String)
    created_at = Column(DateTime)

class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id = Column(Integer, primary_key=True)
    fixture_id = Column(Integer, index=True)
    league_id = Column(Integer, index=True)
    season = Column(Integer, index=True)
    date = Column(DateTime, index=True)
    home_team = Column(String)
    away_team = Column(String)
    home_goals = Column(Integer)
    away_goals = Column(Integer)
    market = Column(String, index=True)
    selection = Column(String)
    bookmaker = Column(String)
    odd = Column(Float)
    model_probability = Column(Float)
    implied_probability = Column(Float)
    edge = Column(Float)
    expected_value = Column(Float)
    stake = Column(Float)
    result = Column(String)
    profit = Column(Float)
    created_at = Column(DateTime)

    __table_args__ = (
        UniqueConstraint("fixture_id", "market", "selection", "bookmaker", name="uq_backtest"),
    )

class TelegramSignal(Base):
    __tablename__ = "telegram_signals"

    id = Column(Integer, primary_key=True)
    fixture_id = Column(Integer, index=True)
    league_id = Column(Integer, index=True)
    date = Column(DateTime, index=True)
    home_team = Column(String)
    away_team = Column(String)
    market = Column(String)
    selection = Column(String)
    bookmaker = Column(String)
    odd = Column(Float)
    model_probability = Column(Float)
    edge = Column(Float)
    expected_value = Column(Float)
    confidence = Column(String)
    suggested_stake_pct = Column(Float)
    telegram_message_id = Column(Integer, nullable=True)
    sent_at = Column(DateTime)

    __table_args__ = (
        UniqueConstraint("fixture_id", "market", "selection", "bookmaker", name="uq_tg_signal"),
    )


class HistoricalTeamStat(Base):
    __tablename__ = "historical_team_stats"

    id = Column(Integer, primary_key=True)
    fixture_id = Column(Integer, index=True)
    team_id = Column(Integer, index=True)
    league_id = Column(Integer, index=True)
    season = Column(Integer, index=True)
    matches = Column(Integer, default=0)
    goals_for_avg = Column(Float, default=0)
    goals_against_avg = Column(Float, default=0)
    btts_rate = Column(Float, default=0)
    over15_rate = Column(Float, default=0)
    over25_rate = Column(Float, default=0)

    __table_args__ = (
        UniqueConstraint("fixture_id", "team_id", name="uq_historical_team_stat"),
    )