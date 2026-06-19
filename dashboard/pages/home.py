import sys
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

import pandas as pd
import streamlit as st

from app.config import settings, validate_world_cup_scope
from app.db.session import SessionLocal
from app.models.entities import Fixture
from app.services.pipeline import run_pipeline
from app.services.recommender import list_recommendations, bet_result, score_label

st.title("BetStarter — FIFA World Cup 2026")
st.caption("Statistical recommendation engine · Analytical tool, not financial advice.")

league, season = validate_world_cup_scope()

with st.sidebar:
    st.caption(f"World Cup {season} · Liga {league}")

bankroll = settings.default_bankroll

if st.button("Atualizar & Analisar", type="primary", use_container_width=True):
    with st.spinner("Buscando jogos e odds, calculando recomendações..."):
        try:
            result = run_pipeline(days=7, past_days=3)
            st.success(
                f"Pipeline concluído — {result['fixtures']} jogos · "
                f"{result['odds']} odds · {result['recommendations']} recomendações"
            )
        except Exception as exc:
            st.error(f"Erro no pipeline: {exc}")
            st.stop()
    st.rerun()

date_selected = st.date_input("Data", value=date.today())

with SessionLocal() as db:
    rows = list_recommendations(db, limit=500, league=league, season=season)
    fixture_map = {
        f.id: f
        for f in db.query(Fixture)
        .filter(Fixture.league_id == league, Fixture.season == season)
        .all()
    }

if not rows:
    st.info("Nenhuma recomendação ainda. Clique em **Atualizar & Analisar** para executar o pipeline.")
    st.stop()

data = []
for r in rows:
    fixture = fixture_map.get(r.fixture_id)
    result = bet_result(r.market, r.selection, fixture)
    stake_r = r.suggested_stake_pct * bankroll
    pnl = stake_r * (r.odd - 1) if result == "WIN" else (-stake_r if result == "RED" else 0.0)

    data.append({
        "Data": r.date,
        "Partida": f"{r.home_team} × {r.away_team}",
        "Mercado": r.market,
        "Seleção": r.selection,
        "Placar": score_label(fixture, r.market),
        "Resultado": result,
        "Odd": r.odd,
        "Modelo %": r.model_probability,
        "Edge": r.edge,
        "EV": r.expected_value,
        "Grau": r.confidence,
        "Stake R$": stake_r,
        "P&L R$": pnl,
    })

df = pd.DataFrame(data)
df["Data"] = pd.to_datetime(df["Data"])

df = df[df["Data"].dt.date == date_selected]
if df.empty:
    st.warning(f"Nenhuma recomendação para {date_selected.strftime('%d/%m/%Y')}.")
    st.stop()

partidas = ["Todos os Jogos"] + sorted(df["Partida"].unique().tolist())
jogo_selected = st.selectbox("Jogo", options=partidas)

if jogo_selected != "Todos os Jogos":
    df = df[df["Partida"] == jogo_selected]
    if df.empty:
        st.warning("Nenhuma recomendação para o jogo selecionado.")
        st.stop()

resolved = df[df["Resultado"].isin(["WIN", "RED"])]
wins = len(resolved[resolved["Resultado"] == "WIN"])
reds = len(resolved[resolved["Resultado"] == "RED"])
n_resolved = wins + reds
hit_rate = wins / n_resolved if n_resolved else 0
total_pnl = resolved["P&L R$"].sum()

st.divider()

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Recomendações", len(df))
c2.metric("WIN", wins)
c3.metric("RED", reds)
c4.metric("Pendentes", len(df[df["Resultado"] == "PENDING"]))
c5.metric("Acerto", f"{hit_rate:.1%}" if n_resolved else "—")
c6.metric("P&L (R$)", f"R$ {total_pnl:+.2f}" if n_resolved else "—")

st.divider()

st.dataframe(
    df.style
    .format({
        "Odd": "{:.2f}",
        "Modelo %": "{:.1%}",
        "Edge": "{:.1%}",
        "EV": "{:.1%}",
        "Stake R$": "R$ {:.2f}",
        "P&L R$": "R$ {:+.2f}",
    })
    .map(
        lambda v: "color: #2ecc71; font-weight:bold" if v == "WIN"
        else ("color: #e74c3c; font-weight:bold" if v == "RED" else ""),
        subset=["Resultado"],
    ),
    use_container_width=True,
    column_config={
        "Data": st.column_config.DatetimeColumn("Data", format="DD/MM HH:mm"),
    },
)
