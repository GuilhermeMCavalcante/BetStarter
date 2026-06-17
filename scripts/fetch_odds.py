import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

import argparse
from app.config import validate_world_cup_scope
from app.db.session import SessionLocal
from app.db.init_db import init_db
from app.services.collector import fetch_and_store_odds

parser = argparse.ArgumentParser(description="Coleta odds da Copa do Mundo.")
parser.add_argument("--league", type=int, default=None)
parser.add_argument("--season", type=int, default=None)
parser.add_argument("--bookmaker", type=int, default=None)
args = parser.parse_args()

league, season = validate_world_cup_scope(args.league, args.season)

init_db()
db = SessionLocal()
try:
    count = fetch_and_store_odds(db, league, season, args.bookmaker)
    print(f"Competicao: FIFA World Cup | league={league} | season={season}")
    print(f"Odds salvas: {count}")
finally:
    db.close()
