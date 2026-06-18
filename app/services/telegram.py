from __future__ import annotations

import logging
from datetime import datetime

import requests
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models.entities import Fixture, Recommendation, TelegramSignal

log = logging.getLogger(__name__)

_BASE_URL = "https://api.telegram.org/bot{token}/{method}"

GRADE_EMOJI = {"A": "🏆", "B": "⭐", "C": "✅", "Low": "⚠️"}
MARKET_EMOJI = {"Over/Under": "📊", "Both Teams Score": "⚽"}


def _api(method: str, payload: dict) -> dict:
    token = settings.telegram_bot_token
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not configured in .env")
    url = _BASE_URL.format(token=token, method=method)
    resp = requests.post(url, json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


def format_signal(rec: Recommendation) -> str:
    grade_em = GRADE_EMOJI.get(rec.confidence, "✅")
    market_em = MARKET_EMOJI.get(rec.market, "📌")
    date_str = rec.date.strftime("%d/%m %H:%M") if rec.date else "—"
    stake_pct = rec.suggested_stake_pct * 100

    ev_indicator = "🟢" if rec.expected_value >= 0.10 else ("🟡" if rec.expected_value >= 0.05 else "🔴")
    edge_indicator = "🟢" if rec.edge >= 0.08 else ("🟡" if rec.edge >= 0.03 else "🔴")

    lines = [
        f"*BetStarter Signal* {grade_em}",
        "",
        f"🗓 `{date_str}`",
        f"⚽ *{rec.home_team}* × *{rec.away_team}*",
        f"{market_em} `{rec.market} — {rec.selection}`",
        f"",
        f"🎯 Odd: *{rec.odd:.2f}*  |  Prob. modelo: *{rec.model_probability:.1%}*",
        f"{ev_indicator} EV: *{rec.expected_value:+.1%}*  |  {edge_indicator} Edge: *{rec.edge:+.1%}*",
        f"📊 Grade: *{rec.confidence}*  |  Stake: *{stake_pct:.1f}%* da banca",
        f"🏦 {rec.bookmaker}",
        "",
        "⚠️ _Análise estatística — não é conselho financeiro._",
    ]
    return "\n".join(lines)


def send_signal(rec: Recommendation, db: Session) -> int | None:
    """Send a single recommendation to Telegram and persist it in telegram_signals.

    Returns the Telegram message_id on success, or None if already sent.
    """
    chat_id = settings.telegram_chat_id
    if not chat_id:
        raise RuntimeError("TELEGRAM_CHAT_ID not configured in .env")

    existing = db.query(TelegramSignal).filter(
        TelegramSignal.fixture_id == rec.fixture_id,
        TelegramSignal.market == rec.market,
        TelegramSignal.selection == rec.selection,
        TelegramSignal.bookmaker == rec.bookmaker,
    ).first()

    if existing:
        log.debug("Signal already sent for fixture=%s market=%s selection=%s", rec.fixture_id, rec.market, rec.selection)
        return None

    text = format_signal(rec)
    response = _api("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    })

    message_id = response.get("result", {}).get("message_id")

    fixture = db.query(Fixture).filter(Fixture.id == rec.fixture_id).first()

    values = {
        "fixture_id": rec.fixture_id,
        "league_id": rec.league_id,
        "date": rec.date,
        "home_team": rec.home_team,
        "away_team": rec.away_team,
        "market": rec.market,
        "selection": rec.selection,
        "bookmaker": rec.bookmaker,
        "odd": rec.odd,
        "model_probability": rec.model_probability,
        "edge": rec.edge,
        "expected_value": rec.expected_value,
        "confidence": rec.confidence,
        "suggested_stake_pct": rec.suggested_stake_pct,
        "telegram_message_id": message_id,
        "sent_at": datetime.utcnow(),
    }
    stmt = sqlite_insert(TelegramSignal).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["fixture_id", "market", "selection", "bookmaker"],
        set_=values,
    )
    db.execute(stmt)
    db.commit()

    log.info("Signal sent: %s × %s | %s %s | odd=%.2f | msg_id=%s",
             rec.home_team, rec.away_team, rec.market, rec.selection, rec.odd, message_id)
    return message_id


def send_batch(recs: list[Recommendation], db: Session) -> tuple[int, int]:
    """Send multiple signals, skipping already-sent ones. Returns (sent, skipped)."""
    sent, skipped = 0, 0
    for rec in recs:
        result = send_signal(rec, db)
        if result is None:
            skipped += 1
        else:
            sent += 1
    return sent, skipped
