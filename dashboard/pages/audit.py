import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Auditoria", layout="wide")

from app.config import validate_world_cup_scope
from app.db.session import SessionLocal
from app.models.entities import Fixture
from app.services.recommender import list_audits


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


st.title("Auditoria das Recomendações")

league, season = validate_world_cup_scope()

status = st.selectbox(
    "Status",
    ["TODOS", "APPROVED", "REJECTED"],
    index=0,
)

limit = st.slider("Quantidade", 50, 1000, 300)

with SessionLocal() as db:
    rows = list_audits(
        db,
        limit=limit,
        league=league,
        season=season,
        status=None if status == "TODOS" else status,
    )

    fixture_map = {
        f.id: f
        for f in db.query(Fixture)
        .filter(Fixture.league_id == league, Fixture.season == season)
        .all()
    }

if not rows:
    st.info("Nenhum registro de auditoria encontrado.")
    st.stop()

data = []

for r in rows:
    fixture = fixture_map.get(r.fixture_id)

    placar = (
        f"{fixture.home_goals} x {fixture.away_goals}"
        if fixture and fixture.home_goals is not None and fixture.away_goals is not None
        else "-"
    )

    resultado = validar_resultado(r, fixture)

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
        "Status": r.status,
        "Motivo": r.reason,
    })

df = pd.DataFrame(data)
df["Data"] = pd.to_datetime(df["Data"])

resolved = df[df["Resultado"].isin(["WIN", "RED"])]

wins = len(resolved[resolved["Resultado"] == "WIN"])
reds = len(resolved[resolved["Resultado"] == "RED"])
total_resolvido = wins + reds

hit_rate = wins / total_resolvido if total_resolvido > 0 else 0
loss_rate = reds / total_resolvido if total_resolvido > 0 else 0

approved = df[df["Status"] == "APPROVED"]
approved_resolved = approved[approved["Resultado"].isin(["WIN", "RED"])]
approved_wins = len(approved_resolved[approved_resolved["Resultado"] == "WIN"])
approved_reds = len(approved_resolved[approved_resolved["Resultado"] == "RED"])
approved_total = approved_wins + approved_reds
approved_hit_rate = approved_wins / approved_total if approved_total > 0 else 0

rejected = df[df["Status"] == "REJECTED"]
rejected_resolved = rejected[rejected["Resultado"].isin(["WIN", "RED"])]
rejected_wins = len(rejected_resolved[rejected_resolved["Resultado"] == "WIN"])
rejected_reds = len(rejected_resolved[rejected_resolved["Resultado"] == "RED"])
rejected_total = rejected_wins + rejected_reds
rejected_hit_rate = rejected_wins / rejected_total if rejected_total > 0 else 0

c1, c2, c3, c4, c5 = st.columns(5)

c1.metric("Registros", len(df))
c2.metric("Resolvidas", total_resolvido)
c3.metric("WIN", wins)
c4.metric("RED", reds)
c5.metric("Hit Rate Geral", f"{hit_rate:.2%}")

c6, c7, c8 = st.columns(3)

c6.metric("Hit Rate Aprovadas", f"{approved_hit_rate:.2%}", f"{approved_total} resolvidas")
c7.metric("Hit Rate Rejeitadas", f"{rejected_hit_rate:.2%}", f"{rejected_total} resolvidas")
c8.metric("Loss Rate Geral", f"{loss_rate:.2%}")

st.dataframe(
    df.style.format({
        "Odd": "{:.2f}",
        "Prob. Modelo": "{:.2%}",
        "Prob. Implícita": "{:.2%}",
        "Edge": "{:.2%}",
        "EV": "{:.2%}",
    }),
    use_container_width=True,
)