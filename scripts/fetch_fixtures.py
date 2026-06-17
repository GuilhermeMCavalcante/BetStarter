import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

import argparse
from app.config import validate_world_cup_scope
from app.db.session import SessionLocal
from app.db.init_db import init_db
from app.services.collector import fetch_and_store_fixtures, calculate_recent_stats

parser = argparse.ArgumentParser(description="Coleta fixtures da Copa do Mundo.")
parser.add_argument("--league", type=int, default=None)
parser.add_argument("--season", type=int, default=None)
parser.add_argument("--days", type=int, default=3)
args = parser.parse_args()

league, season = validate_world_cup_scope(args.league, args.season)

init_db()
db = SessionLocal()
try:
    count = fetch_and_store_fixtures(db, league, season, args.days)
    stats = calculate_recent_stats(db, league, season)
    print(f"Competicao: FIFA World Cup | league={league} | season={season}")
    print(f"Fixtures salvas: {count}")
    print(f"Times com stats atualizadas: {stats}")
finally:
    db.close()
