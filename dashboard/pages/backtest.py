import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import streamlit as st
from sqlalchemy import func
from app.db.session import SessionLocal
from app.models.entities import Fixture, Odd, RecommendationAudit
from app.services.recommender import list_audits, list_recommendations
from app.config import settings, validate_world_cup_scope
from app.models.entities import BacktestResult
from app.services.backtester import run_backtest
st.set_page_config(page_title="Backtest", layout="wide")
st.subheader("Backtest")
limit = st.sidebar.slider("Quantidade", 10, 200, 50)
bankroll = st.sidebar.number_input("Banca", min_value=1.0, value=settings.default_bankroll, step=50.0)
days = st.sidebar.slider("Buscar próximos dias", 1, 30, 7)
league, season = validate_world_cup_scope()

col_bt1, col_bt2 = st.columns(2)

with col_bt1:
    bookmaker_bt = st.selectbox(
        "Casa para backtest",
        ["Superbet", "Bet365", "Betano", "1xBet"],
        index=0,
    )

with col_bt2:
    stake_bt = st.number_input(
        "Stake por entrada",
        min_value=1.0,
        value=1.0,
        step=1.0,
    )

if st.button("Rodar Backtest"):
    with st.spinner("Rodando backtest..."):
        with SessionLocal() as db:
            result = run_backtest(
                db,
                league=league,
                season=season,
                bookmaker=bookmaker_bt,
                stake=stake_bt,
            )

    st.success("Backtest finalizado!")
    st.json(result)

with SessionLocal() as db:
    bt_rows = (
        db.query(BacktestResult)
        .filter(
            BacktestResult.league_id == league,
            BacktestResult.season == season,
        )
        .order_by(BacktestResult.date.asc())
        .all()
    )

if bt_rows:
    bt_data = []

    saldo = 0

    for r in bt_rows:
        saldo += r.profit

        bt_data.append({
            "Data": r.date,
            "Jogo": f"{r.home_team} x {r.away_team}",
            "Placar": f"{r.home_goals} x {r.away_goals}",
            "Mercado": r.market,
            "Entrada": r.selection,
            "Casa": r.bookmaker,
            "Odd": r.odd,
            "Prob. Modelo": r.model_probability,
            "EV": r.expected_value,
            "Resultado": r.result,
            "Lucro": r.profit,
            "Saldo": saldo,
        })

    bt_df = pd.DataFrame(bt_data)

    total_entries = len(bt_df)
    wins = len(bt_df[bt_df["Resultado"] == "WIN"])
    profit = bt_df["Lucro"].sum()
    roi = profit / (total_entries * stake_bt) if total_entries else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Entradas", total_entries)
    c2.metric("Acertos", wins)
    c3.metric("Lucro", f"{profit:.2f}u")
    c4.metric("ROI", f"{roi:.2%}")

    st.line_chart(bt_df.set_index("Data")["Saldo"])

    st.dataframe(
        bt_df.style.format({
            "Odd": "{:.2f}",
            "Prob. Modelo": "{:.2%}",
            "EV": "{:.2%}",
            "Lucro": "{:.2f}",
            "Saldo": "{:.2f}",
        }),
        use_container_width=True,
    )

    st.subheader("ROI por mercado")

    mercado_df = (
        bt_df.groupby(["Mercado", "Entrada"])
        .agg(
            entradas=("Lucro", "count"),
            lucro=("Lucro", "sum"),
        )
        .reset_index()
    )

    mercado_df["ROI"] = mercado_df["lucro"] / mercado_df["entradas"]

    st.dataframe(
        mercado_df.style.format({
            "lucro": "{:.2f}",
            "ROI": "{:.2%}",
        }),
        use_container_width=True,
    )
else:
    st.info("Nenhum backtest encontrado ainda. Clique em Rodar Backtest.")

with SessionLocal() as db:
    fixtures_count = db.query(func.count(Fixture.id)).filter(Fixture.league_id == league, Fixture.season == season).scalar() or 0
    odds_count = db.query(func.count(Odd.id)).join(Fixture, Fixture.id == Odd.fixture_id).filter(Fixture.league_id == league, Fixture.season == season).scalar() or 0
    audit_count = db.query(func.count(RecommendationAudit.id)).filter(RecommendationAudit.league_id == league, RecommendationAudit.season == season).scalar() or 0
    approved_count = db.query(func.count(RecommendationAudit.id)).filter(RecommendationAudit.league_id == league, RecommendationAudit.season == season, RecommendationAudit.status == "APPROVED").scalar() or 0
    rows = list_recommendations(db, limit=limit, league=league, season=season)
    rejected_rows = list_audits(db, limit=80, league=league, season=season, status="REJECTED")
    fixture_rows = db.query(Fixture).filter(Fixture.league_id == league, Fixture.season == season).order_by(Fixture.date.asc()).limit(80).all()

m1, m2, m3, m4 = st.columns(4)
m1.metric("Jogos no banco", fixtures_count)
m2.metric("Odds no banco", odds_count)
m3.metric("Odds analisadas", audit_count)
m4.metric("Entradas aprovadas", approved_count)

tab_rec, tab_games, tab_rejected = st.tabs(["Entradas", "Jogos encontrados", "Rejeitadas / Debug"])

with tab_rec:
    if not rows:
        st.warning("Nenhuma entrada aprovada. Clique em atualizar ou veja a aba 'Rejeitadas / Debug' para entender os filtros.")
    else:
        data = []
        for r in rows:
            data.append({
                "Data": r.date,
                "Jogo": f"{r.home_team} x {r.away_team}",
                "Mercado": r.market,
                "Entrada": r.selection,
                "Casa": r.bookmaker,
                "Odd": r.odd,
                "Prob. Modelo": r.model_probability,
                "Prob. Implicita": r.implied_probability,
                "Edge": r.edge,
                "EV": r.expected_value,
                "Nota": r.confidence,
                "Stake %": r.suggested_stake_pct,
                "Stake R$": r.suggested_stake_pct * bankroll,
            })
        df = pd.DataFrame(data)
        c1, c2, c3 = st.columns(3)
        c1.metric("Entradas", len(df))
        c2.metric("EV medio", f"{df['EV'].mean():.2%}")
        c3.metric("Maior EV", f"{df['EV'].max():.2%}")
        st.dataframe(
            df.style.format({
                "Prob. Modelo": "{:.2%}",
                "Prob. Implicita": "{:.2%}",
                "Edge": "{:.2%}",
                "EV": "{:.2%}",
                "Stake %": "{:.2%}",
                "Stake R$": "R$ {:.2f}",
            }),
            use_container_width=True,
        )

with tab_games:
    if not fixture_rows:
        st.info("Nenhum jogo carregado ainda.")
    else:
        games_df = pd.DataFrame([{
            "Data": f.date,
            "Status": f.status,
            "Jogo": f"{f.home_team} x {f.away_team}",
            "Placar": "" if f.home_goals is None else f"{f.home_goals} x {f.away_goals}",
        } for f in fixture_rows])
        st.dataframe(games_df, use_container_width=True)

with tab_rejected:
    st.caption("Mostra por que odds foram rejeitadas: EV baixo, edge baixo ou mercado fora do filtro.")
    if not rejected_rows:
        st.info("Nenhuma rejeição registrada ainda. Rode o pipeline pelo botão.")
    else:
        rej_df = pd.DataFrame([{
            "Data": r.date,
            "Jogo": f"{r.home_team} x {r.away_team}",
            "Mercado": r.market,
            "Entrada": r.selection,
            "Casa": r.bookmaker,
            "Odd": r.odd,
            "Modelo": r.model_probability,
            "Implícita": r.implied_probability,
            "EV": r.expected_value,
            "Motivo": r.reason,
        } for r in rejected_rows])
        st.dataframe(
            rej_df.style.format({"Modelo": "{:.2%}", "Implícita": "{:.2%}", "EV": "{:.2%}"}),
            use_container_width=True,
        )

def validate_world_cup_scope(league: int | None = None, season: int | None = None) -> tuple[int, int]:
    """Retorna league/season permitidos e bloqueia qualquer competicao fora da Copa."""
    locked_league = settings.world_cup_league_id
    locked_season = settings.world_cup_season

    if not settings.world_cup_only:
        if league is None or season is None:
            raise ValueError("Informe league e season quando WORLD_CUP_ONLY=false.")
        return league, season

    if league is not None and league != locked_league:
        raise ValueError(
            f"Projeto travado para Copa do Mundo: league_id permitido={locked_league}. "
            f"Recebido={league}."
        )
    if season is not None and season != locked_season:
        raise ValueError(
            f"Projeto travado para Copa do Mundo {locked_season}. Recebido season={season}."
        )
    return locked_league, locked_season