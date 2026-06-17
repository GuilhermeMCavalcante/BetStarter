from __future__ import annotations

from datetime import date, timedelta
from typing import Any
import requests

from app.config import settings


class ApiFootballClient:
    def __init__(self):
        if not settings.api_football_key:
            raise RuntimeError("API_FOOTBALL_KEY is not set. Add it to your .env file.")
        self.base_url = "https://v3.football.api-sports.io"
        self.headers = {
            "x-apisports-key": settings.api_football_key,
            "x-rapidapi-host": settings.api_football_host,
        }

    def _get(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        response = requests.get(url, headers=self.headers, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        errors = payload.get("errors")
        if errors:
            raise RuntimeError(f"API-Football error: {errors}")
        return payload.get("response", [])

    def fixtures(self, league: int, season: int, days: int = 3) -> list[dict[str, Any]]:
        today = date.today()
        to_date = today + timedelta(days=days)
        return self._get("fixtures", {
            "league": league,
            "season": season,
            "from": today.isoformat(),
            "to": to_date.isoformat(),
        })

    def fixtures_range(
        self,
        league: int,
        season: int,
        date_from: str,
        date_to: str,
        timezone: str = "America/Sao_Paulo",
    ) -> list[dict[str, Any]]:
        return self._get("fixtures", {
            "league": league,
            "season": season,
            "from": date_from,
            "to": date_to,
            "timezone": timezone,
        })

    def finished_fixtures(self, league: int, season: int, last: int = 10, team: int | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"league": league, "season": season, "last": last, "status": "FT"}
        if team:
            params["team"] = team
        return self._get("fixtures", params)

    def odds(self, league: int, season: int, bookmaker: int | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"league": league, "season": season}
        if bookmaker:
            params["bookmaker"] = bookmaker
        return self._get("odds", params)
