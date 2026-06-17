from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    api_football_key: str = ""
    api_football_host: str = "v3.football.api-sports.io"
    database_url: str = "sqlite:///./bets.db"
    min_ev: float = 0.05
    default_bankroll: float = 1000.0

    # Trava do MVP: por padrao o sistema so aceita Copa do Mundo.
    # Na API-Football, a Copa do Mundo geralmente usa league_id=1.
    world_cup_only: bool = True
    world_cup_league_id: int = 1
    world_cup_season: int = 2026

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()


def validate_world_cup_scope(league: int | None = None, season: int | None = None) -> tuple[int, int]:
    """Retorna league/season permitidos e bloqueia qualquer competicao fora da Copa."""
    locked_league = settings.world_cup_league_id
    locked_season = settings.world_cup_season

    if not settings.world_cup_only:
        if league is None or season is None:
            raise ValueError("Informe league e season quando WORLD_CUP_ONLY=false.")
        return league, season

    if league is not None and league != locked_league:
        raise ValueError(
            f"Projeto travado para Copa do Mundo: league_id permitido={locked_league}. "
            f"Recebido={league}."
        )
    if season is not None and season != locked_season:
        raise ValueError(
            f"Projeto travado para Copa do Mundo {locked_season}. Recebido season={season}."
        )
    return locked_league, locked_season
