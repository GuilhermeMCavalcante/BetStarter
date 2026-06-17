import sys
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Recomendações", layout="wide")

from app.config import settings, validate_world_cup_scope
from app.db.session import SessionLocal
from app.models.entities import Fixture
from app.services.recommender import list_recommendations


def validar_resultado(r, fixture):
    if not fixture or fixture.home_goals is None or fixture.away_goals is None:
        return "PENDENTE"

    total = fixture.home_goals + fixture.away_goals

    if r.market == "Over/Under":
        if r.selection == "Over 1.5":
            return "WIN" if total >= 2 else "RED"
        if r.selection == "Over 2.5":
            return "WIN" if total >= 3 else "RED"
        if r.selection == "Under 3.5":
            return "WIN" if total <= 3 else "RED"

    if r.market == "Both Teams Score":
        btts = fixture.home_goals > 0 and fixture.away_goals > 0
        if r.selection == "Yes":
            return "WIN" if btts else "RED"
        if r.selection == "No":
            return "WIN" if not btts else "RED"

    return "N/A"


st.title("World Cup Bet Recommender MVP")
st.caption("Modelo v1: ratings das seleções + Poisson + filtro de EV. Ferramenta analítica; não garante lucro.")

league, season = validate_world_cup_scope()

st.sidebar.info(f"Competicao: FIFA World Cup\n\nLeague ID: {league}\n\nSeason: {season}")
limit = st.sidebar.slider("Quantidade", 10, 200, 50)
bankroll = st.sidebar.number_input("Banca", min_value=1.0, value=settings.default_bankroll, step=50.0)
days = st.sidebar.slider("Buscar próximos dias", 1, 30, 7)
past_days = st.sidebar.slider("Buscar dias anteriores", 0, 30, 3)

st.sidebar.divider()

date_filter_enabled = st.sidebar.checkbox("Filtrar por data", value=False)

date_selected = None
if date_filter_enabled:
    date_selected = st.sidebar.date_input("Data do jogo")

if st.button("Atualizar recomendações da Copa", type="primary"):
    with st.spinner("Buscando jogos, odds, atualizando ratings e gerando recomendações..."):
        result = subprocess.run(
            [
                sys.executable,
                "scripts/pipeline.py",
                "--past-days", str(past_days),
                "--days", str(days),
            ],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
        )

    if result.returncode == 0:
        st.success("Pipeline executado com sucesso!")
        st.code(result.stdout.strip() or "Atualizado.")
        st.rerun()
    else:
        st.error("Erro ao atualizar recomendações")
        st.code(result.stderr or result.stdout)

with SessionLocal() as db:
    rows = list_recommendations(db, limit=limit, league=league, season=season)

    fixture_map = {
        f.id: f
        for f in db.query(Fixture)
        .filter(Fixture.league_id == league, Fixture.season == season)
        .all()
    }

if not rows:
    st.warning("Nenhuma recomendação encontrada com os filtros atuais.")
    st.stop()

data = []

for r in rows:
    fixture = fixture_map.get(r.fixture_id)

    resultado = validar_resultado(r, fixture)

    placar = (
        f"{fixture.home_goals} x {fixture.away_goals}"
        if fixture and fixture.home_goals is not None and fixture.away_goals is not None
        else "-"
    )

    data.append({
        "Data": r.date,
        "Jogo": f"{r.home_team} x {r.away_team}",
        "Mercado": r.market,
        "Entrada": r.selection,
        "Casa": r.bookmaker,
        "Placar": placar,
        "Resultado": resultado,
        "Odd": r.odd,
        "Prob. Modelo": r.model_probability,
        "Prob. Implícita": r.implied_probability,
        "Edge": r.edge,
        "EV": r.expected_value,
        "Nota": r.confidence,
        "Stake %": r.suggested_stake_pct,
        "Stake R$": r.suggested_stake_pct * bankroll,
    })

df = pd.DataFrame(data)
df["Data"] = pd.to_datetime(df["Data"])

if date_filter_enabled and date_selected:
    df = df[df["Data"].dt.date == date_selected]

if df.empty:
    st.warning("Nenhuma recomendação encontrada para a data selecionada.")
    st.stop()

c1, c2, c3, c4, c5 = st.columns(5)

c1.metric("Entradas", len(df))
c2.metric("WIN", len(df[df["Resultado"] == "WIN"]))
c3.metric("RED", len(df[df["Resultado"] == "RED"]))
c4.metric("Pendentes", len(df[df["Resultado"] == "PENDENTE"]))
c5.metric("Maior EV", f"{df['EV'].max():.2%}")

st.dataframe(
    df.style.format({
        "Odd": "{:.2f}",
        "Prob. Modelo": "{:.2%}",
        "Prob. Implícita": "{:.2%}",
        "Edge": "{:.2%}",
        "EV": "{:.2%}",
        "Stake %": "{:.2%}",
        "Stake R$": "R$ {:.2f}",
    }),
    use_container_width=True,
)