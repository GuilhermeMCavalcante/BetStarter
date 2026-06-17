import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.config import validate_world_cup_scope
from app.db.session import SessionLocal
from app.db.init_db import init_db
from app.services.recommender import generate_recommendations, list_recommendations

league, season = validate_world_cup_scope()

init_db()
db = SessionLocal()
try:
    count = generate_recommendations(db, league=league, season=season)
    print(f"Competicao: FIFA World Cup | league={league} | season={season}")
    print(f"Recomendacoes geradas/atualizadas: {count}")
    for rec in list_recommendations(db, limit=20, league=league, season=season):
        print(
            f"{rec.date} | {rec.home_team} x {rec.away_team} | "
            f"{rec.selection} @ {rec.odd} | EV {rec.expected_value:.2%} | "
            f"Stake {rec.suggested_stake_pct:.2%} | {rec.confidence}"
        )
finally:
    db.close()
