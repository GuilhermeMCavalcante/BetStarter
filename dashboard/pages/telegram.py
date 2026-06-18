import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from app.config import settings, validate_world_cup_scope
from app.db.session import SessionLocal
from app.models.entities import Fixture, TelegramSignal
from app.services.recommender import list_recommendations, bet_result, score_label
from app.services.telegram import format_signal, send_signal, send_batch

st.title("📨 Telegram Signals")
st.caption("Sinais agrupados por dia · Prévia e envio direto para o canal.")

league, season = validate_world_cup_scope()

BR_TZ = ZoneInfo("America/Sao_Paulo")

# ── Config check ───────────────────────────────────────────────────────────────
if not settings.telegram_bot_token or not settings.telegram_chat_id:
    st.error(
        "Telegram não configurado. Adicione no `.env`:\n\n"
        "```\nTELEGRAM_BOT_TOKEN=seu_token\nTELEGRAM_CHAT_ID=seu_chat_id\n```\n\n"
        "Crie um bot via [@BotFather](https://t.me/BotFather)."
    )
    st.stop()

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.success(f"Bot ativo · Chat `{settings.telegram_chat_id}`")
    bankroll = st.number_input("Bankroll (R$)", min_value=1.0, value=settings.default_bankroll, step=50.0)
    st.divider()
    st.subheader("Filtro por data")
    filter_mode = st.radio("Exibir", ["Todos os dias", "Escolher data"], horizontal=True)
    date_filter: date | None = None
    if filter_mode == "Escolher data":
        date_filter = st.date_input("Data", value=date.today())

    st.divider()
    st.subheader("Reset de envios")
    reset_mode = st.radio("Resetar", ["Dia específico", "Tudo"], horizontal=True)
    if reset_mode == "Dia específico":
        reset_date = st.date_input("Data para resetar", value=date.today(), key="reset_date")
        if st.button("🔄 Resetar dia", use_container_width=True):
            with SessionLocal() as db:
                deleted = (
                    db.query(TelegramSignal)
                    .filter(
                        TelegramSignal.league_id == league,
                        TelegramSignal.date >= datetime.combine(reset_date, datetime.min.time()),
                        TelegramSignal.date < datetime.combine(reset_date + timedelta(days=1), datetime.min.time()),
                    )
                    .delete(synchronize_session=False)
                )
                db.commit()
            st.success(f"{deleted} sinal(is) de {reset_date.strftime('%d/%m/%Y')} resetado(s).")
            st.rerun()
    else:
        if st.button("🔄 Resetar tudo", use_container_width=True, type="secondary"):
            with SessionLocal() as db:
                deleted = (
                    db.query(TelegramSignal)
                    .filter(TelegramSignal.league_id == league)
                    .delete(synchronize_session=False)
                )
                db.commit()
            st.success(f"{deleted} sinal(is) resetado(s).")
            st.rerun()

    st.divider()
    st.caption(f"Copa do Mundo {season} · Liga {league}")

# ── Load data ──────────────────────────────────────────────────────────────────
with SessionLocal() as db:
    recs = list_recommendations(db, limit=200, league=league, season=season)
    fixture_map = {
        f.id: f
        for f in db.query(Fixture)
        .filter(Fixture.league_id == league, Fixture.season == season)
        .all()
    }
    already_sent = {
        (s.fixture_id, s.market, s.selection, s.bookmaker)
        for s in db.query(TelegramSignal).filter(TelegramSignal.league_id == league).all()
    }

if not recs:
    st.info("Nenhuma recomendação ainda. Rode o pipeline na página Home primeiro.")
    st.stop()

# ── Helpers ────────────────────────────────────────────────────────────────────
def local_date(rec) -> date:
    if rec.date is None:
        return date.max
    dt = rec.date
    if hasattr(dt, "tzinfo") and dt.tzinfo is None:
        from datetime import timezone
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BR_TZ).date()


# ── Separate pending / sent ────────────────────────────────────────────────────
pending_all = [r for r in recs if (r.fixture_id, r.market, r.selection, r.bookmaker) not in already_sent]
pending = [r for r in pending_all if date_filter is None or local_date(r) == date_filter]

# ── Group pending by local date ────────────────────────────────────────────────


by_day: dict[date, list] = defaultdict(list)
for r in sorted(pending, key=lambda r: r.date or date.max):
    by_day[local_date(r)].append(r)


def day_label(d: date) -> str:
    today = date.today()
    if d == today:
        return f"Hoje — {d.strftime('%d/%m/%Y')}"
    if d == today + timedelta(days=1):
        return f"Amanhã — {d.strftime('%d/%m/%Y')}"
    if d == date.max:
        return "Data indefinida"
    diff = (d - today).days
    if diff > 1:
        return f"Em {diff} dias — {d.strftime('%d/%m/%Y')}"
    return d.strftime("%d/%m/%Y")


# ── Pending section ────────────────────────────────────────────────────────────
total_pending = len(pending)
st.subheader(f"Sinais pendentes — {total_pending} não enviados")

if not by_day:
    st.success("Todos os sinais já foram enviados para o Telegram.")
else:
    label_btn = (f"Enviar todos os {total_pending} sinais de {date_filter.strftime('%d/%m')}"
                 if date_filter else f"Enviar todos os {total_pending} sinais")
    if st.button(label_btn, type="primary", use_container_width=True):
        with st.spinner("Enviando sinais…"):
            with SessionLocal() as db:
                sent_n, skipped_n = send_batch(pending, db)
        st.success(f"{sent_n} sinal(is) enviado(s). {skipped_n} já haviam sido enviados.")
        st.rerun()

    for day in sorted(by_day.keys()):
        day_recs = by_day[day]
        label = day_label(day)

        with st.expander(f"📅 {label} · {len(day_recs)} sinal(is)", expanded=(day <= date.today() + timedelta(days=1))):

            # "Send day" button
            col_title, col_btn = st.columns([5, 1])
            with col_btn:
                if st.button(f"Enviar dia", key=f"day_{day}"):
                    with st.spinner(f"Enviando sinais de {label}…"):
                        with SessionLocal() as db:
                            sent_n, skipped_n = send_batch(day_recs, db)
                    st.success(f"{sent_n} enviado(s).")
                    st.rerun()

            for rec in day_recs:
                fixture = fixture_map.get(rec.fixture_id)
                time_str = rec.date.astimezone(BR_TZ).strftime("%H:%M") if rec.date else "—"
                stake_r = rec.suggested_stake_pct * bankroll

                with st.container(border=True):
                    col_a, col_b, col_c = st.columns([3, 2, 1])
                    with col_a:
                        st.markdown(f"**{rec.home_team} × {rec.away_team}** `{time_str}`")
                        st.markdown(f"`{rec.market} — {rec.selection}` · Odd **{rec.odd:.2f}** · Grade **{rec.confidence}**")
                        st.caption(f"EV {rec.expected_value:.1%} · Edge {rec.edge:.1%} · Prob. {rec.model_probability:.1%} · Stake R$ {stake_r:.2f}")
                    with col_b:
                        with st.popover("Prévia da mensagem"):
                            st.code(format_signal(rec), language=None)
                    with col_c:
                        if st.button("Enviar", key=f"send_{rec.fixture_id}_{rec.market}_{rec.selection}"):
                            try:
                                with SessionLocal() as db:
                                    msg_id = send_signal(rec, db)
                                if msg_id:
                                    st.success("Enviado!")
                                else:
                                    st.warning("Já enviado.")
                                st.rerun()
                            except Exception as exc:
                                st.error(str(exc))


# ── Sent history ───────────────────────────────────────────────────────────────
st.divider()
st.subheader("Histórico de enviados")

with SessionLocal() as db:
    signals = (
        db.query(TelegramSignal)
        .filter(TelegramSignal.league_id == league)
        .order_by(TelegramSignal.date.asc(), TelegramSignal.sent_at.desc())
        .limit(300)
        .all()
    )

if date_filter is not None:
    signals = [s for s in signals if (s.date.date() if s.date else None) == date_filter]

if not signals:
    st.info("Nenhum sinal enviado ainda." if date_filter is None else f"Nenhum sinal enviado em {date_filter.strftime('%d/%m/%Y')}.")
    st.stop()

# Group history by match date too
hist_by_day: dict[date, list] = defaultdict(list)
for s in signals:
    d = s.date.date() if s.date else date.max
    hist_by_day[d].append(s)

# Summary metrics
all_results = [bet_result(s.market, s.selection, fixture_map.get(s.fixture_id)) for s in signals]
wins = all_results.count("WIN")
reds = all_results.count("RED")
n_resolved = wins + reds

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total enviados", len(signals))
c2.metric("WIN", wins)
c3.metric("RED", reds)
c4.metric("Hit Rate", f"{wins/n_resolved:.1%}" if n_resolved else "—")

st.divider()

for day in sorted(hist_by_day.keys()):
    day_signals = hist_by_day[day]
    label = day_label(day)
    day_results = [bet_result(s.market, s.selection, fixture_map.get(s.fixture_id)) for s in day_signals]
    day_wins = day_results.count("WIN")
    day_reds = day_results.count("RED")
    day_pending = day_results.count("PENDING")
    summary = f"✅ {day_wins} WIN · ❌ {day_reds} RED · ⏳ {day_pending} pendente(s)"

    with st.expander(f"📅 {label} · {len(day_signals)} sinal(is) · {summary}", expanded=False):
        rows = []
        for s in day_signals:
            fixture = fixture_map.get(s.fixture_id)
            result = bet_result(s.market, s.selection, fixture)
            time_str = s.date.strftime("%H:%M") if s.date else "—"
            rows.append({
                "Horário": time_str,
                "Partida": f"{s.home_team} × {s.away_team}",
                "Mercado": s.market,
                "Seleção": s.selection,
                "Placar": score_label(fixture, s.market),
                "Resultado": result,
                "Odd": s.odd,
                "EV": s.expected_value,
                "Grade": s.confidence,
            })

        df = pd.DataFrame(rows)
        st.dataframe(
            df.style
            .format({"Odd": "{:.2f}", "EV": "{:.1%}"})
            .map(
                lambda v: "color: #2ecc71; font-weight:bold" if v == "WIN"
                else ("color: #e74c3c; font-weight:bold" if v == "RED" else ""),
                subset=["Resultado"],
            ),
            use_container_width=True,
        )
