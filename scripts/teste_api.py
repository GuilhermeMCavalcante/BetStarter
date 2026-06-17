import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.services.api_football import ApiFootballClient

client = ApiFootballClient()

data = client.fixtures_range(
    league=1,
    season=2022,
    date_from="2022-11-20",
    date_to="2022-12-18",
)

print("Jogos encontrados:", len(data))

for item in data[:5]:
    fixture = item["fixture"]
    teams = item["teams"]
    goals = item.get("goals", {})
    print(
        fixture["id"],
        fixture["date"],
        teams["home"]["name"],
        "x",
        teams["away"]["name"],
        goals.get("home"),
        goals.get("away"),
    )