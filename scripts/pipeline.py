import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
from app.config import validate_world_cup_scope
from app.services.pipeline import run_pipeline

parser = argparse.ArgumentParser(description="BetStarter pipeline — collect fixtures, odds and generate recommendations.")
parser.add_argument("--league", type=int, default=None, help="Override league ID (requires WORLD_CUP_ONLY=false)")
parser.add_argument("--season", type=int, default=None, help="Override season (requires WORLD_CUP_ONLY=false)")
parser.add_argument("--days", type=int, default=7, help="Number of days ahead to collect fixtures")
parser.add_argument("--past-days", type=int, default=10, help="Number of days back to include")
args = parser.parse_args()

validate_world_cup_scope(args.league, args.season)

result = run_pipeline(days=args.days, past_days=args.past_days)
print(result)
