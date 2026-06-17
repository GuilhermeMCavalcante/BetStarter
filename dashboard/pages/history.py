import sys
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import streamlit as st
from sqlalchemy import func
from app.config import settings, validate_world_cup_scope
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models.entities import Fixture
from app.services.api_football import ApiFootballClient
from app.services.collector import upsert_fixture

st.set_page_config(page_title="Histórico", layout="wide")
st.subheader("Histórico da Copa")

season_history = st.selectbox(
    "Temporada histórica",
    [2022, 2026],
    index=0,
)

with SessionLocal() as db:
    history_rows = (
        db.query(Fixture)
        .filter(
            Fixture.league_id == 1,
            Fixture.season == season_history,
        )
        .order_by(Fixture.date.asc())
        .all()
    )

if not history_rows:
    st.info("Nenhum jogo histórico encontrado para essa temporada.")
else:
    history_data = []

    for f in history_rows:
        history_data.append({
            "Data": f.date,
            "Jogo": f"{f.home_team} x {f.away_team}",
            "Placar": (
                f"{f.home_goals} x {f.away_goals}"
                if f.home_goals is not None and f.away_goals is not None
                else "-"
            ),
            "Status": f.status,
            "Home ID": f.home_team_id,
            "Away ID": f.away_team_id,
            "Fixture API ID": f.api_fixture_id,
        })

    history_df = pd.DataFrame(history_data)

    c1, c2, c3 = st.columns(3)
    c1.metric("Jogos", len(history_df))
    c2.metric("Finalizados", len(history_df[history_df["Status"].isin(["FT", "AET", "PEN"])]))
    c3.metric("Pendentes", len(history_df[~history_df["Status"].isin(["FT", "AET", "PEN"])]))

    st.dataframe(history_df, use_container_width=True)

st.subheader("Importar Copa do Mundo")
season_import = st.number_input(
    "Ano da Copa",
    min_value=1930,
    max_value=2030,
    value=2022,
    step=4,
)

if st.button("Importar jogos da Copa"):
    with st.spinner(f"Importando jogos da Copa {season_import}..."):
        client = ApiFootballClient()

        rows = client.fixtures_range(
            league=1,
            season=int(season_import),
            date_from=f"{int(season_import)}-01-01",
            date_to=f"{int(season_import)}-12-31",
        )

        with SessionLocal() as db:
            for row in rows:
                upsert_fixture(
                    db,
                    row,
                    league_id=1,
                    season=int(season_import),
                )

            db.commit()

    st.success(f"Copa {season_import} importada com sucesso: {len(rows)} jogos.")
    st.rerun()