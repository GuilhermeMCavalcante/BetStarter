import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
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

st.set_page_config(page_title="BetStarter", layout="wide", page_icon="⚽")

st.title("BetStarter — FIFA World Cup 2026")
st.caption("Statistical recommendation engine · Analytical tool, not financial advice.")

league, season = validate_world_cup_scope()

with st.sidebar:
    st.header("Settings")
    bankroll = st.number_input("Bankroll (R$)", min_value=1.0, value=settings.default_bankroll, step=50.0)
    days = st.slider("Look ahead (days)", 1, 30, 7)
    past_days = st.slider("Look back (days)", 0, 30, 3)
    limit = st.slider("Max rows", 10, 200, 50)
    st.divider()
    date_filter = st.checkbox("Filter by date")
    date_selected = st.date_input("Date") if date_filter else None
    st.divider()
    st.caption(f"World Cup {season} · League {league}")

if st.button("Update & Analyze", type="primary", use_container_width=True):
    with st.spinner("Fetching fixtures and odds, computing recommendations..."):
        try:
            result = run_pipeline(days=days, past_days=past_days)
            st.success(
                f"Pipeline complete — {result['fixtures']} fixtures · "
                f"{result['odds']} odds · {result['recommendations']} recommendations"
            )
        except Exception as exc:
            st.error(f"Pipeline error: {exc}")
            st.stop()
    st.rerun()

with SessionLocal() as db:
    rows = list_recommendations(db, limit=limit, league=league, season=season)
    fixture_map = {
        f.id: f
        for f in db.query(Fixture)
        .filter(Fixture.league_id == league, Fixture.season == season)
        .all()
    }

if not rows:
    st.info("No recommendations yet. Click **Update & Analyze** to run the pipeline.")
    st.stop()

data = []
for r in rows:
    fixture = fixture_map.get(r.fixture_id)
    result = bet_result(r.market, r.selection, fixture)
    stake_r = r.suggested_stake_pct * bankroll
    pnl = stake_r * (r.odd - 1) if result == "WIN" else (-stake_r if result == "RED" else 0.0)

    data.append({
        "Date": r.date,
        "Match": f"{r.home_team} × {r.away_team}",
        "Market": r.market,
        "Selection": r.selection,
        "Score": score_label(fixture),
        "Result": result,
        "Odd": r.odd,
        "Model %": r.model_probability,
        "Edge": r.edge,
        "EV": r.expected_value,
        "Grade": r.confidence,
        "Stake R$": stake_r,
        "P&L R$": pnl,
    })

df = pd.DataFrame(data)
df["Date"] = pd.to_datetime(df["Date"])

if date_filter and date_selected:
    df = df[df["Date"].dt.date == date_selected]
    if df.empty:
        st.warning(f"No recommendations for {date_selected}.")
        st.stop()

resolved = df[df["Result"].isin(["WIN", "RED"])]
wins = len(resolved[resolved["Result"] == "WIN"])
reds = len(resolved[resolved["Result"] == "RED"])
n_resolved = wins + reds
hit_rate = wins / n_resolved if n_resolved else 0
total_pnl = resolved["P&L R$"].sum()

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Recommendations", len(df))
c2.metric("WIN", wins)
c3.metric("RED", reds)
c4.metric("Pending", len(df[df["Result"] == "PENDING"]))
c5.metric("Hit Rate", f"{hit_rate:.1%}" if n_resolved else "—")
c6.metric("P&L (R$)", f"R$ {total_pnl:+.2f}" if n_resolved else "—")

st.divider()

st.dataframe(
    df.style
    .format({
        "Odd": "{:.2f}",
        "Model %": "{:.1%}",
        "Edge": "{:.1%}",
        "EV": "{:.1%}",
        "Stake R$": "R$ {:.2f}",
        "P&L R$": "R$ {:+.2f}",
    })
    .map(
        lambda v: "color: #2ecc71; font-weight:bold" if v == "WIN"
        else ("color: #e74c3c; font-weight:bold" if v == "RED" else ""),
        subset=["Result"],
    ),
    use_container_width=True,
    column_config={
        "Date": st.column_config.DatetimeColumn("Date", format="DD/MM HH:mm"),
    },
)
