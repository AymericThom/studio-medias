"""Notifications sur ton téléphone avec ntfy (gratuit, sans compte) : appli « ntfy » sur Android/iPhone,
abonnement au « sujet » secret affiché dans Réglages. Le studio prévient quand un post est prêt, publié, ou en erreur.
"""
from __future__ import annotations

import logging
import secrets

import requests

from .config import load_settings, save_settings

log = logging.getLogger("studio.notify")
SERVER = "https://ntfy.sh"


def topic() -> str:
    s = load_settings()
    t = s.get("ntfy_topic")
    if not t:
        t = "studio-medias-" + secrets.token_hex(6)     # nom difficile à deviner = canal privé
        save_settings({"ntfy_topic": t})
    return t


def send(title: str, message: str, tags: list[str] | None = None, priority: int = 3, click: str = "",
         kind: str = "ready") -> bool:
    """kind : ready (post prêt), published (publié), error (erreur). Respecte les choix faits dans Réglages."""
    s = load_settings()
    if not s.get("notify", True) or not s.get(f"notify_{kind}", True):
        return False
    payload = {"topic": topic(), "title": title[:200], "message": message[:3000], "tags": tags or [], "priority": priority}
    url = click or s.get("public_url", "")
    if url:
        payload["click"] = url
    try:
        r = requests.post(SERVER, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as ex:
        log.debug("Notification impossible : %s", ex)
        return False
