import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import streamlit as st

from app.config import settings, validate_world_cup_scope
from app.db.session import SessionLocal
from app.models.entities import BacktestResult
from app.services.backtester import run_backtest

st.set_page_config(page_title="Backtest — BetStarter", layout="wide", page_icon="🔬")

st.title("Backtest")
st.caption("Simulate the model against historical World Cup data to evaluate its edge.")

league, season = validate_world_cup_scope()

with st.sidebar:
    bankroll = st.number_input("Bankroll (R$)", min_value=1.0, value=settings.default_bankroll, step=50.0)

col1, col2 = st.columns(2)
with col1:
    bookmaker_bt = st.selectbox("Bookmaker", ["Superbet", "Bet365", "Betano", "1xBet"])
with col2:
    stake_bt = st.number_input("Stake per entry (units)", min_value=0.1, value=1.0, step=0.5)

if st.button("Run Backtest", type="primary"):
    with st.spinner("Running backtest against historical fixtures..."):
        with SessionLocal() as db:
            result = run_backtest(db, league=league, season=season, bookmaker=bookmaker_bt, stake=stake_bt)
    st.success("Backtest complete.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Entries", result["entries"])
    c2.metric("Hit rate", f"{result['hit_rate']:.1%}")
    c3.metric("Profit", f"{result['profit']:+.2f}u")
    c4.metric("ROI", f"{result['roi']:.1%}")

st.divider()

with SessionLocal() as db:
    bt_rows = (
        db.query(BacktestResult)
        .filter(BacktestResult.league_id == league, BacktestResult.season == season)
        .order_by(BacktestResult.date.asc())
        .all()
    )

if not bt_rows:
    st.info("No backtest results yet. Click **Run Backtest** above.")
    st.stop()

bt_data = []
running_pnl = 0.0
for r in bt_rows:
    running_pnl += r.profit
    bt_data.append({
        "Date": r.date,
        "Match": f"{r.home_team} × {r.away_team}",
        "Score": f"{r.home_goals} × {r.away_goals}",
        "Market": r.market,
        "Selection": r.selection,
        "Odd": r.odd,
        "Model %": r.model_probability,
        "EV": r.expected_value,
        "Result": r.result,
        "Profit": r.profit,
        "Running P&L": running_pnl,
    })

bt_df = pd.DataFrame(bt_data)
bt_df["Date"] = pd.to_datetime(bt_df["Date"])

total_entries = len(bt_df)
wins = len(bt_df[bt_df["Result"] == "WIN"])
profit = bt_df["Profit"].sum()
roi = profit / (total_entries * stake_bt) if total_entries else 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Entries", total_entries)
c2.metric("Wins", wins)
c3.metric("Profit", f"{profit:+.2f}u")
c4.metric("ROI", f"{roi:.1%}")

st.subheader("Equity Curve")
st.line_chart(bt_df.set_index("Date")["Running P&L"])

st.subheader("ROI by Market")
market_df = (
    bt_df.groupby(["Market", "Selection"])
    .agg(entries=("Profit", "count"), profit=("Profit", "sum"))
    .reset_index()
)
market_df["ROI"] = market_df["profit"] / (market_df["entries"] * stake_bt)
st.dataframe(
    market_df.style.format({"profit": "{:+.2f}", "ROI": "{:.1%}"}),
    use_container_width=True,
)

st.subheader("All Entries")
st.dataframe(
    bt_df.style.format({
        "Odd": "{:.2f}",
        "Model %": "{:.1%}",
        "EV": "{:.1%}",
        "Profit": "{:+.2f}",
        "Running P&L": "{:+.2f}",
    }),
    use_container_width=True,
    column_config={
        "Date": st.column_config.DatetimeColumn("Date", format="DD/MM/YYYY"),
    },
)
