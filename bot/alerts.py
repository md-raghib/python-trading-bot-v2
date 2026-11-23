"""Telegram alerts. Optional: with no token configured, alerts only go to the log.

Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env (never in code or git).
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request

log = logging.getLogger("bot.alerts")


class Alerts:
    def __init__(self, token: str | None = None, chat_id: str | None = None,
                 min_repeat_seconds: int = 600) -> None:
        self.token = token if token is not None else os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID", "")
        self.min_repeat = min_repeat_seconds
        self._last_sent: dict[str, float] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, text: str, dedupe_key: str | None = None) -> None:
        """Best effort: an alert failure must never crash the bot."""
        log.info("ALERT: %s", text)
        if dedupe_key:
            last = self._last_sent.get(dedupe_key, 0.0)
            if time.time() - last < self.min_repeat:
                return
            self._last_sent[dedupe_key] = time.time()
        if not self.enabled:
            return
        try:
            body = json.dumps({"chat_id": self.chat_id, "text": f"🤖 {text}"}).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                data=body, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10).read()
        except Exception as e:  # noqa: BLE001
            log.warning("telegram alert failed: %s", e)
