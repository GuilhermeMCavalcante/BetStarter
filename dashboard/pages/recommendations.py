import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import streamlit as st

from app.config import settings, validate_world_cup_scope
from app.db.session import SessionLocal
from app.models.entities import Fixture, Recommendation
from app.services.recommender import list_recommendations, bet_result, score_label

st.title("Performance")
st.caption("P&L evolution and market breakdown for all resolved recommendations.")

league, season = validate_world_cup_scope()

with st.sidebar:
    bankroll = st.number_input("Bankroll (R$)", min_value=1.0, value=settings.default_bankroll, step=50.0)
    limit = st.slider("Max rows", 10, 500, 200)

with SessionLocal() as db:
    rows = list_recommendations(db, limit=limit, league=league, season=season)
    fixture_map = {
        f.id: f
        for f in db.query(Fixture)
        .filter(Fixture.league_id == league, Fixture.season == season)
        .all()
    }

if not rows:
    st.info("No recommendations found. Run the pipeline on the Home page first.")
    st.stop()

data = []
for r in rows:
    fixture = fixture_map.get(r.fixture_id)
    result = bet_result(r.market, r.selection, fixture)
    stake_r = r.suggested_stake_pct * bankroll
    pnl = stake_r * (r.odd - 1) if result == "WIN" else (-stake_r if result == "RED" else None)

    data.append({
        "Date": r.date,
        "Match": f"{r.home_team} × {r.away_team}",
        "Market": r.market,
        "Selection": r.selection,
        "Score": score_label(fixture, r.market),
        "Result": result,
        "Odd": r.odd,
        "EV": r.expected_value,
        "Grade": r.confidence,
        "Stake R$": stake_r,
        "P&L R$": pnl,
    })

df = pd.DataFrame(data)
df["Date"] = pd.to_datetime(df["Date"])
df_resolved = df[df["Result"].isin(["WIN", "RED"])].copy()

if df_resolved.empty:
    st.info("No resolved bets yet — results will appear as matches are played.")
    st.stop()

# Summary
wins = len(df_resolved[df_resolved["Result"] == "WIN"])
reds = len(df_resolved[df_resolved["Result"] == "RED"])
n = wins + reds
hit_rate = wins / n if n else 0
total_pnl = df_resolved["P&L R$"].sum()
avg_odd = df_resolved["Odd"].mean()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Resolved bets", n)
c2.metric("Hit rate", f"{hit_rate:.1%}")
c3.metric("Total P&L", f"R$ {total_pnl:+.2f}")
c4.metric("Avg odd", f"{avg_odd:.2f}")
c5.metric("ROI", f"{total_pnl / df_resolved['Stake R$'].sum():.1%}" if df_resolved["Stake R$"].sum() else "—")

st.divider()

# Equity curve
df_resolved_sorted = df_resolved.sort_values("Date")
df_resolved_sorted["Cumulative P&L"] = df_resolved_sorted["P&L R$"].cumsum()

st.subheader("Equity Curve")
st.line_chart(df_resolved_sorted.set_index("Date")["Cumulative P&L"])

st.divider()

# Market breakdown
st.subheader("ROI by Market")
market_df = (
    df_resolved.groupby(["Market", "Selection"])
    .agg(
        bets=("P&L R$", "count"),
        wins=("Result", lambda x: (x == "WIN").sum()),
        pnl=("P&L R$", "sum"),
        stake=("Stake R$", "sum"),
    )
    .reset_index()
)
market_df["Hit Rate"] = market_df["wins"] / market_df["bets"]
market_df["ROI"] = market_df["pnl"] / market_df["stake"]

st.dataframe(
    market_df.style.format({
        "pnl": "R$ {:.2f}",
        "Hit Rate": "{:.1%}",
        "ROI": "{:.1%}",
    }),
    use_container_width=True,
)

st.divider()

# Full table
st.subheader("All resolved bets")
st.dataframe(
    df_resolved.style
    .format({
        "Odd": "{:.2f}",
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
