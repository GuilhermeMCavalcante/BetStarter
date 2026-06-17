import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

import streamlit as st

from app.db.session import SessionLocal
from app.models.entities import Fixture
from app.services.api_football import ApiFootballClient
from app.services.collector import upsert_fixture

st.set_page_config(page_title="History — BetStarter", layout="wide", page_icon="📅")

st.title("Match History")
st.caption("Historical World Cup fixtures. Import past editions to enable backtesting.")

FINISHED_STATUSES = {"FT", "AET", "PEN"}

season_history = st.selectbox("Season", [2022, 2026], index=0)

with SessionLocal() as db:
    history_rows = (
        db.query(Fixture)
        .filter(Fixture.league_id == 1, Fixture.season == season_history)
        .order_by(Fixture.date.asc())
        .all()
    )

if history_rows:
    finished = [f for f in history_rows if f.status in FINISHED_STATUSES]
    pending = [f for f in history_rows if f.status not in FINISHED_STATUSES]

    c1, c2, c3 = st.columns(3)
    c1.metric("Total fixtures", len(history_rows))
    c2.metric("Finished", len(finished))
    c3.metric("Upcoming / TBD", len(pending))

    history_data = [
        {
            "Date": f.date,
            "Match": f"{f.home_team} × {f.away_team}",
            "Score": f"{f.home_goals} × {f.away_goals}" if f.home_goals is not None else "-",
            "Status": f.status,
        }
        for f in history_rows
    ]

    import pandas as pd
    history_df = pd.DataFrame(history_data)
    st.dataframe(
        history_df,
        use_container_width=True,
        column_config={
            "Date": st.column_config.DatetimeColumn("Date", format="DD/MM/YYYY HH:mm"),
        },
    )
else:
    st.info(f"No fixtures found for World Cup {season_history}. Import them below.")

st.divider()
st.subheader("Import World Cup Season")
st.caption("Fetch all fixtures for a past edition from API-Football and store them locally.")

season_import = st.number_input("Year", min_value=1930, max_value=2030, value=2022, step=4)

if st.button("Import fixtures", type="primary"):
    with st.spinner(f"Fetching World Cup {season_import} fixtures from API-Football..."):
        try:
            client = ApiFootballClient()
            rows = client.fixtures_range(
                league=1,
                season=int(season_import),
                date_from=f"{int(season_import)}-01-01",
                date_to=f"{int(season_import)}-12-31",
            )
            with SessionLocal() as db:
                for row in rows:
                    upsert_fixture(db, row, league_id=1, season=int(season_import))
                db.commit()
            st.success(f"Imported {len(rows)} fixtures for World Cup {season_import}.")
        except Exception as exc:
            st.error(f"Import failed: {exc}")
    st.rerun()
