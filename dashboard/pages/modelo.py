import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

import pandas as pd
import streamlit as st

from app.config import settings, validate_world_cup_scope
from app.db.session import SessionLocal
from app.models.entities import TeamRating, BacktestResult
from app.services.worldcup_model import (
    DEFAULT_TEAM_RATINGS,
    elo_update_ratings,
    seed_team_ratings,
)
from app.services.backtester import run_backtest

st.title("Model Intelligence")
st.caption("Current team ratings, model parameters, calibration, and learning from results.")

league, season = validate_world_cup_scope()

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Actions")
    if st.button("Update Ratings from Results", type="primary", use_container_width=True, help="Apply Elo updates from all completed matches this season"):
        with st.spinner("Replaying match history and updating ratings…"):
            with SessionLocal() as db:
                n = elo_update_ratings(db, league=league, season=season)
        st.success(f"Ratings updated from {n} completed matches.")
        st.rerun()

    if st.button("Reset to Manual Priors", use_container_width=True, help="Restore all ratings to the original hand-crafted values"):
        with SessionLocal() as db:
            seed_team_ratings(db)
        st.info("Ratings reset to manual priors.")
        st.rerun()

    st.divider()

    if st.button("Run Backtest (current params)", use_container_width=True):
        with st.spinner("Running backtest on completed fixtures…"):
            with SessionLocal() as db:
                summary = run_backtest(db, league=league, season=season, bookmaker=settings.target_bookmaker, stake=1.0)
        st.json(summary)

    st.divider()
    st.caption(f"World Cup {season} · League {league}")


# ── Team Ratings ───────────────────────────────────────────────────────────────
st.subheader("Team Ratings")

with SessionLocal() as db:
    db_ratings = {r.team_name: (r.rating, r.source) for r in db.query(TeamRating).all()}

rating_rows = []
for team, manual_r in DEFAULT_TEAM_RATINGS.items():
    db_r, source = db_ratings.get(team, (manual_r, "manual_v1"))
    delta = db_r - manual_r
    rating_rows.append({
        "Team": team,
        "Current Rating": round(db_r, 1),
        "Manual Prior": manual_r,
        "Δ from Prior": round(delta, 1),
        "Source": source,
    })

rating_df = pd.DataFrame(rating_rows).sort_values("Current Rating", ascending=False).reset_index(drop=True)

col_l, col_r = st.columns([2, 1])

with col_l:
    st.dataframe(
        rating_df.style
        .format({"Current Rating": "{:.1f}", "Manual Prior": "{:.0f}", "Δ from Prior": "{:+.1f}"})
        .map(
            lambda v: "color: #2ecc71" if v > 0 else ("color: #e74c3c" if v < 0 else ""),
            subset=["Δ from Prior"],
        ),
        use_container_width=True,
        height=500,
    )

with col_r:
    top = rating_df.head(20).sort_values("Current Rating")
    st.bar_chart(top.set_index("Team")["Current Rating"], height=500)


# ── Model Parameters ───────────────────────────────────────────────────────────
st.divider()
st.subheader("Model Parameters")

params = {
    "Base home expected goals": 1.22,
    "Base away expected goals": 1.05,
    "Elo K-factor": 6.0,
    "Max rating stat weight": "45%",
    "Poisson weight (when trend available)": "72%",
    "Trend weight (when trend available)": "28%",
    "Shrinkage factor": "0.96 × prob + 0.02",
    "Max confidence score": 92,
    "Min confidence to recommend": 55,
    "Min EV to recommend": f"{settings.min_ev:.0%}",
    "Target bookmaker": settings.target_bookmaker,
    "Markets": "Over 0.5 / 1.5 / 2.5 / 3.5 | Under 3.5 | BTTS Yes/No",
}

p1, p2 = st.columns(2)
items = list(params.items())
for i, (k, v) in enumerate(items):
    (p1 if i % 2 == 0 else p2).metric(k, v)


# ── Calibration ────────────────────────────────────────────────────────────────
st.divider()
st.subheader("Model Calibration")
st.caption("How often did the model's predicted probability match the actual win rate? (Requires completed backtest data.)")

with SessionLocal() as db:
    bt_rows = db.query(BacktestResult).filter(
        BacktestResult.league_id == league,
        BacktestResult.season == season,
    ).all()

if not bt_rows:
    st.info("No backtest data yet. Use the sidebar button to run a backtest first.")
else:
    bt_data = [{"prob": r.model_probability, "won": r.result == "WIN", "market": r.market, "selection": r.selection, "profit": r.profit} for r in bt_rows]
    bt_df = pd.DataFrame(bt_data)

    # Calibration by probability bucket
    bt_df["bucket"] = pd.cut(
        bt_df["prob"],
        bins=[0, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 1.01],
        labels=["<50%", "50-55%", "55-60%", "60-65%", "65-70%", "70-75%", "75-80%", "80-85%", "85-90%", ">90%"],
    )
    cal = (
        bt_df.groupby("bucket", observed=True)
        .agg(bets=("won", "count"), win_rate=("won", "mean"), avg_prob=("prob", "mean"))
        .reset_index()
    )
    cal["Predicted %"] = (cal["avg_prob"] * 100).round(1)
    cal["Actual %"] = (cal["win_rate"] * 100).round(1)
    cal["Gap"] = (cal["Actual %"] - cal["Predicted %"]).round(1)

    ca, cb = st.columns(2)
    with ca:
        st.markdown("**Predicted vs Actual win rate by probability bucket**")
        chart_df = cal[cal["bets"] > 0].set_index("bucket")[["Predicted %", "Actual %"]]
        st.bar_chart(chart_df)

    with cb:
        st.dataframe(
            cal[["bucket", "bets", "Predicted %", "Actual %", "Gap"]]
            .style.format({"Predicted %": "{:.1f}", "Actual %": "{:.1f}", "Gap": "{:+.1f}"})
            .map(lambda v: "color: #2ecc71" if v > 2 else ("color: #e74c3c" if v < -2 else ""), subset=["Gap"]),
            use_container_width=True,
        )

    # Market accuracy breakdown
    st.divider()
    st.subheader("Accuracy by Market")
    market_cal = (
        bt_df.groupby(["market", "selection"], observed=True)
        .agg(
            bets=("won", "count"),
            wins=("won", "sum"),
            avg_model_prob=("prob", "mean"),
            total_profit=("profit", "sum"),
        )
        .reset_index()
    )
    market_cal["Hit Rate"] = market_cal["wins"] / market_cal["bets"]
    market_cal["ROI"] = market_cal["total_profit"] / market_cal["bets"]
    market_cal["Avg Model Prob"] = market_cal["avg_model_prob"]

    st.dataframe(
        market_cal[["market", "selection", "bets", "Hit Rate", "Avg Model Prob", "ROI", "total_profit"]]
        .rename(columns={"market": "Market", "selection": "Selection", "bets": "Bets", "total_profit": "Total Profit"})
        .style.format({
            "Hit Rate": "{:.1%}",
            "Avg Model Prob": "{:.1%}",
            "ROI": "{:+.1%}",
            "Total Profit": "{:+.2f}",
        })
        .map(lambda v: "color: #2ecc71" if isinstance(v, float) and v > 0 else ("color: #e74c3c" if isinstance(v, float) and v < 0 else ""), subset=["ROI", "Total Profit"]),
        use_container_width=True,
    )

    # Equity curve from backtest
    st.divider()
    st.subheader("Backtest Equity Curve")
    bt_sorted = bt_df.sort_values("prob").reset_index(drop=True)
    bt_sorted["Cumulative Profit"] = bt_sorted["profit"].cumsum()
    st.line_chart(bt_sorted["Cumulative Profit"])
