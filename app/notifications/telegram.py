"""Telegram notifier — drift alerts (Phase 1.3) + daily digest (Phase 4).

Why Telegram (not email/Slack/Discord):
- Free, instant push to mobile, works internationally.
- No corporate inbox graveyard like email.
- Single bot token + chat ID — minimal config friction.

Setup:
1. DM @BotFather on Telegram, ``/newbot``, capture the token.
2. DM your new bot anything (forces a chat). Then:
   ``curl https://api.telegram.org/bot<TOKEN>/getUpdates`` →
   read ``result[0].message.chat.id``.
3. Set env vars on Railway / .env.laptop:
   - ``TELEGRAM_BOT_TOKEN``
   - ``TELEGRAM_CHAT_ID``

When both env vars are empty the notifier no-ops silently — code is
deploy-safe before the operator has set them up. The first failed call
is logged at WARN; subsequent failures within the same process tick are
logged at DEBUG to avoid spam.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.core.config import SETTINGS

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org"
_HTTP_TIMEOUT = 5.0
_warned_unconfigured = False


def configured() -> bool:
    return bool(SETTINGS.TELEGRAM_BOT_TOKEN and SETTINGS.TELEGRAM_CHAT_ID)


async def send_message(
    text: str,
    *,
    parse_mode: str = "Markdown",
    disable_notification: bool = False,
) -> bool:
    """POST to ``sendMessage``. Returns True on success, False otherwise.

    Never raises — Telegram outages or misconfig must not crash the lifespan
    loop they're called from. Caller should not condition critical logic on
    delivery success.
    """
    global _warned_unconfigured
    if not configured():
        if not _warned_unconfigured:
            logger.info(
                "telegram: not configured (TELEGRAM_BOT_TOKEN/CHAT_ID empty); "
                "drift alerts + digest will be silent until set"
            )
            _warned_unconfigured = True
        return False

    url = f"{_TELEGRAM_API}/bot{SETTINGS.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": SETTINGS.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_notification": disable_notification,
    }
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            r = await client.post(url, json=payload)
            if r.status_code == 200:
                return True
            logger.warning(
                "telegram: send failed status=%d body=%s",
                r.status_code,
                r.text[:200],
            )
            return False
    except Exception as e:  # noqa: BLE001
        logger.warning("telegram: send exception: %s", e)
        return False
