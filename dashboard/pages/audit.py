import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import streamlit as st

from app.config import validate_world_cup_scope
from app.db.session import SessionLocal
from app.models.entities import Fixture
from app.services.recommender import list_audits, bet_result

st.set_page_config(page_title="Audit — BetStarter", layout="wide", page_icon="🔍")

st.title("Audit Trail")
st.caption("Every odd evaluated by the model — approved and rejected — with the reason.")

league, season = validate_world_cup_scope()

status_filter = st.selectbox("Status", ["ALL", "APPROVED", "REJECTED"], index=0)
limit = st.slider("Max rows", 50, 1000, 300)

with SessionLocal() as db:
    rows = list_audits(
        db,
        limit=limit,
        league=league,
        season=season,
        status=None if status_filter == "ALL" else status_filter,
    )
    fixture_map = {
        f.id: f
        for f in db.query(Fixture)
        .filter(Fixture.league_id == league, Fixture.season == season)
        .all()
    }

if not rows:
    st.info("No audit records found. Run the pipeline on the Home page first.")
    st.stop()

data = []
for r in rows:
    fixture = fixture_map.get(r.fixture_id)
    result = bet_result(r.market, r.selection, fixture)
    score = (
        f"{fixture.home_goals} × {fixture.away_goals}"
        if fixture and fixture.home_goals is not None
        else "-"
    )
    data.append({
        "Date": r.date,
        "Match": f"{r.home_team} × {r.away_team}",
        "Market": r.market,
        "Selection": r.selection,
        "Score": score,
        "Outcome": result,
        "Status": r.status,
        "Odd": r.odd,
        "Model %": r.model_probability,
        "Implied %": r.implied_probability,
        "Edge": r.edge,
        "EV": r.expected_value,
        "Reason": r.reason,
    })

df = pd.DataFrame(data)
df["Date"] = pd.to_datetime(df["Date"])

approved = df[df["Status"] == "APPROVED"]
rejected = df[df["Status"] == "REJECTED"]
resolved = df[df["Outcome"].isin(["WIN", "RED"])]
wins = len(resolved[resolved["Outcome"] == "WIN"])
reds = len(resolved[resolved["Outcome"] == "RED"])
n_resolved = wins + reds
hit_rate = wins / n_resolved if n_resolved else 0

approved_resolved = approved[approved["Outcome"].isin(["WIN", "RED"])]
approved_wins = len(approved_resolved[approved_resolved["Outcome"] == "WIN"])
approved_n = len(approved_resolved)
approved_hit = approved_wins / approved_n if approved_n else 0

rejected_resolved = rejected[rejected["Outcome"].isin(["WIN", "RED"])]
rejected_wins = len(rejected_resolved[rejected_resolved["Outcome"] == "WIN"])
rejected_n = len(rejected_resolved)
rejected_hit = rejected_wins / rejected_n if rejected_n else 0

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Records", len(df))
c2.metric("Approved", len(approved))
c3.metric("Rejected", len(rejected))
c4.metric("Hit rate (approved)", f"{approved_hit:.1%}" if approved_n else "—", f"{approved_n} resolved")
c5.metric("Hit rate (rejected)", f"{rejected_hit:.1%}" if rejected_n else "—", f"{rejected_n} resolved")

st.divider()

st.dataframe(
    df.style
    .format({
        "Odd": "{:.2f}",
        "Model %": "{:.1%}",
        "Implied %": "{:.1%}",
        "Edge": "{:.1%}",
        "EV": "{:.1%}",
    })
    .map(
        lambda v: "color: #2ecc71" if v == "APPROVED" else ("color: #e74c3c" if v == "REJECTED" else ""),
        subset=["Status"],
    )
    .map(
        lambda v: "color: #2ecc71; font-weight:bold" if v == "WIN"
        else ("color: #e74c3c; font-weight:bold" if v == "RED" else ""),
        subset=["Outcome"],
    ),
    use_container_width=True,
    column_config={
        "Date": st.column_config.DatetimeColumn("Date", format="DD/MM HH:mm"),
        "Reason": st.column_config.TextColumn("Reason", width="large"),
    },
)
