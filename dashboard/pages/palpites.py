import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

from collections import defaultdict
from datetime import date, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from app.config import validate_world_cup_scope
from app.db.session import SessionLocal
from app.models.entities import Fixture, Odd, TeamRecentStat
from app.services.worldcup_model import calculate_1x2, canonical_team_name

st.set_page_config(page_title="Palpites — BetStarter", layout="wide", page_icon="🎯")

st.title("🎯 Palpites")
st.caption("Previsão de resultado (1×2) baseada no modelo Poisson com ratings e estatísticas recentes.")

league, season = validate_world_cup_scope()
BR_TZ = ZoneInfo("America/Sao_Paulo")

TIP_LABEL = {"1": "Casa", "X": "Empate", "2": "Visitante"}
TIP_COLOR = {"1": "#3498db", "X": "#95a5a6", "2": "#e67e22"}
TIP_EMOJI = {"1": "🏠", "X": "🤝", "2": "✈️"}

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filtros")
    show_finished = st.checkbox("Incluir jogos encerrados", value=False)
    days_ahead = st.slider("Próximos (dias)", 1, 30, 14)
    st.divider()
    st.caption(f"Copa do Mundo {season} · Liga {league}")

# ── Load data ──────────────────────────────────────────────────────────────────
with SessionLocal() as db:
    fixtures = (
        db.query(Fixture)
        .filter(Fixture.league_id == league, Fixture.season == season)
        .order_by(Fixture.date.asc())
        .all()
    )
    team_stats = {
        s.team_id: s
        for s in db.query(TeamRecentStat)
        .filter(TeamRecentStat.league_id == league, TeamRecentStat.season == season)
        .all()
    }
    # Load bookmaker odds for comparison (Match Winner market)
    bookmaker_odds: dict[int, dict] = defaultdict(dict)
    for odd in db.query(Odd).filter(Odd.market == "Match Winner").all():
        if odd.selection in ("Home", "Draw", "Away"):
            bookmaker_odds[odd.fixture_id][odd.selection] = odd.odd

if not fixtures:
    st.info("Nenhum jogo encontrado. Rode o pipeline na Home primeiro.")
    st.stop()

# ── Filter ─────────────────────────────────────────────────────────────────────
today = date.today()
cutoff = today + timedelta(days=days_ahead)

def local_date(f) -> date:
    if f.date is None:
        return date.max
    dt = f.date
    if hasattr(dt, "tzinfo") and dt.tzinfo is None:
        from datetime import timezone
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BR_TZ).date()

def day_label(d: date) -> str:
    if d == today:
        return f"Hoje — {d.strftime('%d/%m/%Y')}"
    if d == today + timedelta(days=1):
        return f"Amanhã — {d.strftime('%d/%m/%Y')}"
    if d == date.max:
        return "Data indefinida"
    return d.strftime("%A, %d/%m/%Y").capitalize()

visible = []
for f in fixtures:
    fd = local_date(f)
    is_finished = f.status in ("FT", "AET", "PEN")
    if is_finished and not show_finished:
        continue
    if not is_finished and fd > cutoff:
        continue
    visible.append(f)

if not visible:
    st.info("Nenhum jogo no período selecionado.")
    st.stop()

# ── Group by day ───────────────────────────────────────────────────────────────
by_day: dict[date, list] = defaultdict(list)
for f in visible:
    by_day[local_date(f)].append(f)

# ── Render ─────────────────────────────────────────────────────────────────────
with SessionLocal() as db:
    for day in sorted(by_day.keys()):
        day_fixtures = by_day[day]
        st.subheader(f"📅 {day_label(day)}")

        for f in day_fixtures:
            home_stats = team_stats.get(f.home_team_id)
            away_stats = team_stats.get(f.away_team_id)
            pred = calculate_1x2(db, f, home_stats, away_stats)

            tip = pred["tip"]
            time_str = f.date.astimezone(BR_TZ).strftime("%H:%M") if f.date else "—"
            is_finished = f.status in ("FT", "AET", "PEN")

            with st.container(border=True):
                # Header row
                h_left, h_mid, h_right = st.columns([2, 1, 2])
                with h_left:
                    st.markdown(f"### {f.home_team}")
                with h_mid:
                    st.markdown(
                        f"<div style='text-align:center; padding-top:8px'>"
                        f"<span style='font-size:0.85rem; color:#888'>{time_str}</span><br>"
                        f"<span style='font-size:1.1rem; font-weight:bold'>VS</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                with h_right:
                    st.markdown(f"### {f.away_team}")

                # Result (if finished)
                if is_finished and f.home_goals is not None:
                    actual = "1" if f.home_goals > f.away_goals else ("X" if f.home_goals == f.away_goals else "2")
                    hit = tip == actual
                    result_str = f"**{f.home_goals} × {f.away_goals}**  ·  {'✅ Acertou' if hit else '❌ Errou'}"
                    st.markdown(
                        f"<div style='text-align:center; color:{'#2ecc71' if hit else '#e74c3c'}'>{result_str}</div>",
                        unsafe_allow_html=True,
                    )

                st.divider()

                # Probability bars
                p_cols = st.columns(3)
                for col, (key, label, prob) in zip(p_cols, [
                    ("1", f"🏠 {f.home_team}", pred["home"]),
                    ("X", "🤝 Empate", pred["draw"]),
                    ("2", f"✈️ {f.away_team}", pred["away"]),
                ]):
                    is_tip = key == tip
                    border = f"border: 2px solid {TIP_COLOR[key]};" if is_tip else ""
                    bg = f"background:{TIP_COLOR[key]}18;" if is_tip else ""
                    badge = " 🏆 Palpite" if is_tip else ""
                    col.markdown(
                        f"<div style='text-align:center; padding:10px; border-radius:8px; {border}{bg}'>"
                        f"<div style='font-size:0.8rem; color:#888'>{label}{badge}</div>"
                        f"<div style='font-size:1.6rem; font-weight:bold; color:{TIP_COLOR[key]}'>{prob:.1%}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

                st.divider()

                # Expected goals + most likely score + bookmaker odds
                info_cols = st.columns(3)
                with info_cols[0]:
                    st.caption("Placar mais provável")
                    ml = pred["most_likely_score"]
                    st.markdown(f"**{ml[0]} × {ml[1]}** &nbsp; `{pred['most_likely_score_prob']:.1%}`", unsafe_allow_html=True)
                with info_cols[1]:
                    st.caption("Gols esperados (λ)")
                    st.markdown(f"Casa **{pred['expected_home_goals']}** &nbsp;·&nbsp; Visitante **{pred['expected_away_goals']}**", unsafe_allow_html=True)
                with info_cols[2]:
                    bk = bookmaker_odds.get(f.api_fixture_id, {})
                    if bk:
                        st.caption("Odds casa de apostas")
                        h_odd = bk.get("Home", "—")
                        d_odd = bk.get("Draw", "—")
                        a_odd = bk.get("Away", "—")
                        st.markdown(
                            f"🏠 `{h_odd if isinstance(h_odd, str) else f'{h_odd:.2f}'}` &nbsp;"
                            f"🤝 `{d_odd if isinstance(d_odd, str) else f'{d_odd:.2f}'}` &nbsp;"
                            f"✈️ `{a_odd if isinstance(a_odd, str) else f'{a_odd:.2f}'}`",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.caption("Odds")
                        st.markdown("_Não disponível_")

                st.caption(f"Confiança: {pred['confidence']} · {pred['reason']}")

        st.divider()

# ── Summary table ──────────────────────────────────────────────────────────────
with st.expander("📋 Tabela resumo", expanded=False):
    summary_rows = []
    with SessionLocal() as db:
        for f in visible:
            h_stats = team_stats.get(f.home_team_id)
            a_stats = team_stats.get(f.away_team_id)
            pred = calculate_1x2(db, f, h_stats, a_stats)
            tip = pred["tip"]
            ml = pred["most_likely_score"]

            actual = None
            hit = None
            if f.status in ("FT", "AET", "PEN") and f.home_goals is not None:
                actual = "1" if f.home_goals > f.away_goals else ("X" if f.home_goals == f.away_goals else "2")
                hit = "✅" if tip == actual else "❌"

            summary_rows.append({
                "Data": f.date,
                "Partida": f"{f.home_team} × {f.away_team}",
                "Palpite": f"{TIP_EMOJI[tip]} {TIP_LABEL[tip]}",
                "Casa %": pred["home"],
                "Empate %": pred["draw"],
                "Visitante %": pred["away"],
                "Placar Provável": f"{ml[0]}–{ml[1]}",
                "Resultado": hit or "⏳",
            })

    sum_df = pd.DataFrame(summary_rows)
    st.dataframe(
        sum_df.style.format({
            "Casa %": "{:.1%}",
            "Empate %": "{:.1%}",
            "Visitante %": "{:.1%}",
        }),
        use_container_width=True,
        column_config={"Data": st.column_config.DatetimeColumn("Data", format="DD/MM HH:mm")},
    )

    finished_preds = [(r["Palpite"], r["Resultado"]) for r in summary_rows if r["Resultado"] in ("✅", "❌")]
    if finished_preds:
        hits = sum(1 for _, r in finished_preds if r == "✅")
        st.metric("Acerto dos palpites encerrados", f"{hits}/{len(finished_preds)} ({hits/len(finished_preds):.0%})")
