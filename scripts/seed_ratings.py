import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.services.worldcup_model import seed_team_ratings

init_db()
with SessionLocal() as db:
    print({"ratings_seeded": seed_team_ratings(db)})
