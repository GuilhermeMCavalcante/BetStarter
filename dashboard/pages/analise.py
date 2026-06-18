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
from app.models.entities import Fixture, Recommendation, TeamRecentStat, TeamRating
from app.services.recommender import bet_result
from app.services.worldcup_model import (
    calculate_corners_probability,
    calculate_market_probability,
    canonical_team_name,
)

st.title("🔬 Análise")
st.caption("Explorador de partidas, estatísticas por time e breakdown de mercados.")

league, season = validate_world_cup_scope()

# ── Load base data ─────────────────────────────────────────────────────────────
with SessionLocal() as db:
    all_fixtures = (
        db.query(Fixture)
        .filter(Fixture.league_id == league, Fixture.season == season)
        .order_by(Fixture.date.asc())
        .all()
    )
    all_recs = db.query(Recommendation).filter(Recommendation.league_id == league).all()
    team_stats = {
        s.team_id: s
        for s in db.query(TeamRecentStat)
        .filter(TeamRecentStat.league_id == league, TeamRecentStat.season == season)
        .all()
    }
    team_ratings = {r.team_name: r.rating for r in db.query(TeamRating).all()}

fixture_map = {f.id: f for f in all_fixtures}

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_explorer, tab_teams, tab_markets, tab_corners = st.tabs([
    "⚽ Explorador de Partidas",
    "📊 Stats por Time",
    "📈 Breakdown de Mercados",
    "🟡 Escanteios",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Fixture Explorer
# ══════════════════════════════════════════════════════════════════════════════
with tab_explorer:
    st.subheader("Explorador de Partidas")
    st.caption("Selecione um jogo para ver as probabilidades do modelo em todos os mercados.")

    upcoming = [f for f in all_fixtures if f.status not in ("FT", "AET", "PEN")]
    finished = [f for f in all_fixtures if f.status in ("FT", "AET", "PEN")]

    col_filter, _ = st.columns([2, 3])
    with col_filter:
        show_type = st.radio("Jogos", ["Próximos", "Encerrados"], horizontal=True)

    fixture_list = upcoming if show_type == "Próximos" else finished
    if not fixture_list:
        st.info("Nenhum jogo encontrado. Rode o pipeline na Home primeiro.")
    else:
        fixture_labels = {
            f.id: f"{f.date.strftime('%d/%m %H:%M') if f.date else '—'}  {f.home_team} × {f.away_team}"
            for f in fixture_list
        }
        selected_id = st.selectbox("Jogo", options=list(fixture_labels.keys()), format_func=lambda x: fixture_labels[x])
        fixture = fixture_map[selected_id]
        home_stats = team_stats.get(fixture.home_team_id)
        away_stats = team_stats.get(fixture.away_team_id)

        col_a, col_b = st.columns(2)
        with col_a:
            home_r = team_ratings.get(canonical_team_name(fixture.home_team), 70)
            st.metric(fixture.home_team, f"Rating {home_r:.0f}")
            if home_stats:
                st.caption(
                    f"Jogos: {home_stats.matches} · Gols/jogo: {home_stats.goals_for_avg:.1f} marcados / "
                    f"{home_stats.goals_against_avg:.1f} sofridos · BTTS: {home_stats.btts_rate:.0%} · "
                    f"Over 1.5: {home_stats.over15_rate:.0%} · Over 2.5: {home_stats.over25_rate:.0%}"
                )
                if home_stats.corners_for_avg is not None:
                    st.caption(f"Escanteios: {home_stats.corners_for_avg:.1f} a favor / {home_stats.corners_against_avg:.1f} contra")
            else:
                st.caption("Sem estatísticas recentes.")

        with col_b:
            away_r = team_ratings.get(canonical_team_name(fixture.away_team), 70)
            st.metric(fixture.away_team, f"Rating {away_r:.0f}")
            if away_stats:
                st.caption(
                    f"Jogos: {away_stats.matches} · Gols/jogo: {away_stats.goals_for_avg:.1f} marcados / "
                    f"{away_stats.goals_against_avg:.1f} sofridos · BTTS: {away_stats.btts_rate:.0%} · "
                    f"Over 1.5: {away_stats.over15_rate:.0%} · Over 2.5: {away_stats.over25_rate:.0%}"
                )
                if away_stats.corners_for_avg is not None:
                    st.caption(f"Escanteios: {away_stats.corners_for_avg:.1f} a favor / {away_stats.corners_against_avg:.1f} contra")
            else:
                st.caption("Sem estatísticas recentes.")

        if fixture.home_goals is not None:
            st.info(f"Resultado: **{fixture.home_goals} × {fixture.away_goals}** · Escanteios: {fixture.home_corners or '—'} × {fixture.away_corners or '—'}")

        st.divider()
        st.subheader("Probabilidades do modelo")

        with SessionLocal() as db:
            markets = [
                ("Over/Under", "Over 1.5"),
                ("Over/Under", "Over 2.5"),
                ("Over/Under", "Over 3.5"),
                ("Over/Under", "Under 3.5"),
                ("Both Teams Score", "Yes"),
                ("Both Teams Score", "No"),
                ("Corners Over/Under", "Over 8.5"),
                ("Corners Over/Under", "Over 9.5"),
                ("Corners Over/Under", "Over 10.5"),
                ("Corners Over/Under", "Under 9.5"),
                ("Corners Over/Under", "Under 10.5"),
            ]
            rows = []
            for market, selection in markets:
                if market == "Corners Over/Under":
                    out = calculate_corners_probability(home_stats, away_stats, selection)
                else:
                    out = calculate_market_probability(db, fixture, home_stats, away_stats, market, selection)
                rows.append({
                    "Mercado": market,
                    "Seleção": selection,
                    "Prob. Modelo": out.probability,
                    "Confiança": out.confidence_score,
                    "λ Casa": round(out.expected_home_goals, 2),
                    "λ Visitante": round(out.expected_away_goals, 2),
                    "Razão": out.reason,
                })

        model_df = pd.DataFrame(rows)
        st.dataframe(
            model_df.style.format({
                "Prob. Modelo": "{:.1%}",
                "λ Casa": "{:.2f}",
                "λ Visitante": "{:.2f}",
            }).map(lambda v: "color: #2ecc71; font-weight:bold" if isinstance(v, float) and v >= 0.65
                   else ("color: #e74c3c" if isinstance(v, float) and v < 0.50 else ""), subset=["Prob. Modelo"]),
            use_container_width=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Team Stats
# ══════════════════════════════════════════════════════════════════════════════
with tab_teams:
    st.subheader("Estatísticas por Time")

    rows = []
    for f in all_fixtures:
        for team_id, team_name in [(f.home_team_id, f.home_team), (f.away_team_id, f.away_team)]:
            if any(r["Time"] == team_name for r in rows):
                continue
            s = team_stats.get(team_id)
            rating = team_ratings.get(canonical_team_name(team_name), 70)
            rows.append({
                "Time": team_name,
                "Rating": round(rating, 1),
                "Jogos": s.matches if s else 0,
                "Gols/jogo (marcados)": round(s.goals_for_avg, 2) if s else None,
                "Gols/jogo (sofridos)": round(s.goals_against_avg, 2) if s else None,
                "BTTS %": s.btts_rate if s else None,
                "Over 1.5 %": s.over15_rate if s else None,
                "Over 2.5 %": s.over25_rate if s else None,
                "Escanteios (a favor)": round(s.corners_for_avg, 1) if s and s.corners_for_avg else None,
                "Escanteios (contra)": round(s.corners_against_avg, 1) if s and s.corners_against_avg else None,
            })

    if not rows:
        st.info("Nenhum dado de time disponível. Rode o pipeline na Home.")
    else:
        teams_df = pd.DataFrame(rows).sort_values("Rating", ascending=False).reset_index(drop=True)
        st.dataframe(
            teams_df.style.format({
                "Rating": "{:.1f}",
                "Gols/jogo (marcados)": "{:.2f}",
                "Gols/jogo (sofridos)": "{:.2f}",
                "BTTS %": "{:.0%}",
                "Over 1.5 %": "{:.0%}",
                "Over 2.5 %": "{:.0%}",
                "Escanteios (a favor)": "{:.1f}",
                "Escanteios (contra)": "{:.1f}",
            }, na_rep="—"),
            use_container_width=True,
            height=600,
        )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Market Breakdown
# ══════════════════════════════════════════════════════════════════════════════
with tab_markets:
    st.subheader("Breakdown de Recomendações por Mercado")

    if not all_recs:
        st.info("Nenhuma recomendação gerada ainda.")
    else:
        rec_rows = []
        for r in all_recs:
            fx = fixture_map.get(r.fixture_id)
            result = bet_result(r.market, r.selection, fx)
            rec_rows.append({
                "Mercado": r.market,
                "Seleção": r.selection,
                "Resultado": result,
                "Odd": r.odd,
                "EV": r.expected_value,
                "Edge": r.edge,
                "Prob. Modelo": r.model_probability,
                "Grade": r.confidence,
            })

        rec_df = pd.DataFrame(rec_rows)

        # Summary by market+selection
        resolved_df = rec_df[rec_df["Resultado"].isin(["WIN", "RED"])]
        total_df = rec_df.groupby(["Mercado", "Seleção"]).agg(
            Total=("Resultado", "count"),
            Pendentes=("Resultado", lambda x: (x == "PENDING").sum()),
        ).reset_index()

        if not resolved_df.empty:
            perf_df = resolved_df.groupby(["Mercado", "Seleção"]).agg(
                Resolvidos=("Resultado", "count"),
                WIN=("Resultado", lambda x: (x == "WIN").sum()),
                Avg_EV=("EV", "mean"),
                Avg_Odd=("Odd", "mean"),
            ).reset_index()
            perf_df["Hit Rate"] = perf_df["WIN"] / perf_df["Resolvidos"]
            summary = total_df.merge(perf_df, on=["Mercado", "Seleção"], how="left")
        else:
            summary = total_df
            summary["Hit Rate"] = None

        fmt = {"Avg_EV": "{:.1%}", "Avg_Odd": "{:.2f}", "Hit Rate": "{:.0%}"}
        st.dataframe(summary.style.format(fmt, na_rep="—"), use_container_width=True)

        st.divider()
        st.subheader("Distribuição de EV por mercado")
        if not rec_df.empty:
            ev_chart = rec_df.groupby("Mercado")["EV"].mean().reset_index()
            st.bar_chart(ev_chart.set_index("Mercado")["EV"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Corners
# ══════════════════════════════════════════════════════════════════════════════
with tab_corners:
    st.subheader("Modelo de Escanteios")

    # Teams with corner data
    corner_rows = []
    for f in all_fixtures:
        for team_id, team_name in [(f.home_team_id, f.home_team), (f.away_team_id, f.away_team)]:
            if any(r["Time"] == team_name for r in corner_rows):
                continue
            s = team_stats.get(team_id)
            if s and s.corners_for_avg is not None:
                corner_rows.append({
                    "Time": team_name,
                    "Jogos c/ dados": s.matches,
                    "Escanteios/jogo (a favor)": round(s.corners_for_avg, 1),
                    "Escanteios/jogo (contra)": round(s.corners_against_avg, 1),
                    "Total médio": round(s.corners_for_avg + s.corners_against_avg, 1),
                    "Over 9.5 %": s.over95_corners_rate,
                    "Over 10.5 %": s.over105_corners_rate,
                })

    if not corner_rows:
        st.info(
            "Ainda não há dados de escanteios coletados. "
            "Rode o pipeline na Home — o sistema irá buscar as estatísticas dos jogos encerrados "
            "via `/fixtures/statistics` da API-Football automaticamente."
        )
        st.markdown("""
        **O que está pronto:**
        - ✅ Coleta de escanteios por jogo (`home_corners`, `away_corners` em `Fixture`)
        - ✅ Médias por time (`corners_for_avg`, `corners_against_avg`, `over95_corners_rate`, `over105_corners_rate`)
        - ✅ Modelo Poisson de escanteios (`calculate_corners_probability`)
        - ✅ Mercados: Over/Under 8.5, 9.5, 10.5, 11.5 escanteios
        - ✅ Blend com histórico quando disponível (65% Poisson + 35% taxa real)
        - ✅ Integrado ao recomendador (aparece junto com gols no dashboard)

        **Próximo passo:** rode o pipeline para coletar dados de jogos já encerrados.
        """)
    else:
        corner_df = pd.DataFrame(corner_rows).sort_values("Total médio", ascending=False).reset_index(drop=True)
        st.dataframe(
            corner_df.style.format({
                "Escanteios/jogo (a favor)": "{:.1f}",
                "Escanteios/jogo (contra)": "{:.1f}",
                "Total médio": "{:.1f}",
                "Over 9.5 %": "{:.0%}",
                "Over 10.5 %": "{:.0%}",
            }, na_rep="—"),
            use_container_width=True,
        )

        st.divider()
        # Corner model preview for upcoming fixtures
        st.subheader("Previsão de Escanteios — Próximos Jogos")
        upcoming_fx = [f for f in all_fixtures if f.status not in ("FT", "AET", "PEN")]
        if not upcoming_fx:
            st.info("Nenhum jogo próximo encontrado.")
        else:
            preview_rows = []
            for f in upcoming_fx[:15]:
                h_stats = team_stats.get(f.home_team_id)
                a_stats = team_stats.get(f.away_team_id)
                out95 = calculate_corners_probability(h_stats, a_stats, "Over 9.5")
                out105 = calculate_corners_probability(h_stats, a_stats, "Over 10.5")
                preview_rows.append({
                    "Data": f.date,
                    "Partida": f"{f.home_team} × {f.away_team}",
                    "λ Total (esp.)": round(out95.expected_home_goals + out95.expected_away_goals, 1),
                    "Over 9.5": out95.probability,
                    "Over 10.5": out105.probability,
                    "Confiança": out95.confidence_score,
                })

            prev_df = pd.DataFrame(preview_rows)
            st.dataframe(
                prev_df.style.format({
                    "λ Total (esp.)": "{:.1f}",
                    "Over 9.5": "{:.1%}",
                    "Over 10.5": "{:.1%}",
                }).map(lambda v: "color: #2ecc71; font-weight:bold" if isinstance(v, float) and v >= 0.65
                       else ("color: #e74c3c" if isinstance(v, float) and v < 0.50 else ""), subset=["Over 9.5"]),
                use_container_width=True,
                column_config={"Data": st.column_config.DatetimeColumn("Data", format="DD/MM HH:mm")},
            )
