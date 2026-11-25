"""Chemins, réglages (enregistrés depuis le site dans data/settings.json) et définition des médias."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import logging
import os
import sys
import threading
import time
from collections import deque
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
POSTS = DATA / "posts"
BRAND = DATA / "brand"
WEB = ROOT / "web"
ASSETS = ROOT / "assets"
SETTINGS_FILE = DATA / "settings.json"
USER_AGENT = "Mozilla/5.0 (compatible; StudioMedias/1.0; news digest)"
TIMEZONE = "Europe/Paris"

# Mode hébergé (GitHub Actions) : les clés viennent des « secrets » GitHub et ne sont JAMAIS écrites sur le disque,
# car le dossier data/ est mis en cache entre deux passages.
CLOUD = os.environ.get("STUDIO_CLOUD") == "1"
VAULT = DATA / "jetons_ig.json"          # jetons Instagram prolongés, chiffrés avec le jeton d'origine (secret GitHub)
_ENV_KEYS = {"gemini_key": "GEMINI_API_KEY", "pexels_key": "PEXELS_API_KEY", "x_api_key": "X_API_KEY",
             "x_api_secret": "X_API_SECRET", "ntfy_topic": "NTFY_TOPIC", "public_static_url": "PUBLIC_STATIC_URL",
             "buffer_key": "BUFFER_KEY_1", "buffer_key2": "BUFFER_KEY_2", "buffer_key3": "BUFFER_KEY_3",
             "buffer_key4": "BUFFER_KEY_4", "buffer_key5": "BUFFER_KEY_5", "buffer_key6": "BUFFER_KEY_6"}
_SECRET_KEYS = ("gemini_key", "pexels_key", "x_api_key", "x_api_secret", "ntfy_topic", "password",
                "buffer_key", "buffer_key2", "buffer_key3", "buffer_key4", "buffer_key5", "buffer_key6")
_PUB_SECRET_KEYS = ("ig_token", "x_token", "x_secret")
_MASKED: set[str] = set()

DEFAULT_SETTINGS = {
    "gemini_key": "",
    "pexels_key": "",
    "password": "",               # mot de passe d'accès au site (indispensable si le studio est en ligne)
    "ai_quality": "eco",          # eco = Flash-Lite d'abord (beaucoup d'appels gratuits) ; max = Flash d'abord
    "auto": True,                 # génération automatique tant que le studio tourne
    "check_every_min": 10,        # lecture des sources (gratuit, sans IA) toutes les X minutes
    "hot_sources": 3,             # un sujet est "chaud" s'il est repris par au moins X médias
    "min_gap_min": 20,            # écart minimum entre deux générations d'un même média
    "max_silence_h": 3,           # au moins un post toutes les X heures (pendant les heures actives)
    "hours": [7, 23],             # heures actives (la nuit : seulement les très grosses infos)
    "per_run": 2,                 # nouveaux posts max par génération et par média
    "max_per_day": 10,            # posts max par jour et par média
    "press_photo": True,
    "browser_reader": True,
    # --- notifications téléphone (ntfy, gratuit)
    "notify": True, "notify_ready": True, "notify_published": True, "notify_error": True, "ntfy_topic": "",
    # --- publication automatique (Buffer : X, Instagram, TikTok)
    "buffer_key": "",
    "buffer_key2": "", "buffer_key3": "", "buffer_key4": "", "buffer_key5": "", "buffer_key6": "",  # 1 compte Buffer gratuit par média
    "publish_rhythm": {},         # {x|instagram|tiktok|hub: {max, gap}} : remplace le rythme par défaut de chaque réseau
    "hub": {"enabled": False, "x": "", "name": "GROS TITRE"},  # compte X généraliste : le meilleur des 5 médias
    "auto_judiciaire": True,      # publier seul le politico-judiciaire vérifié à 100 % et repris par 2 médias (jamais les drames)
    "recap": True,                # « L'essentiel du jour » : carrousel récapitulatif chaque soir, par média
    "recap_hour": 19,
    "publish": {},                # {media_id: {enabled, ig_user_id, ig_token, x_token, x_secret, + comptes Buffer x/instagram/tiktok}}
    "x_api_key": "", "x_api_secret": "",   # app développeur X (une seule pour tous les comptes)
    "auto_sensitive": False,      # publier aussi automatiquement les sujets sensibles vérifiés
    "auto_enquetes": False,       # publier aussi automatiquement les enquêtes
    "public_static_url": "",      # mode GitHub : adresse GitHub Pages où sont publiées les images
    "publish_max_per_day": 12,    # posts auto max par jour et par compte
    "publish_gap_min": 45,        # écart minimum entre deux posts auto sur un même compte
    "public_url": "",             # adresse publique fixe du studio s'il est hébergé
    "tunnel": False,              # adresse publique automatique via Cloudflare (exige un mot de passe)
    "pub_secret": "",       # lire les sites qui bloquent les robots avec un vrai navigateur (Chrome/Edge)
    "enquete_every_days": 3,      # une enquête de fond tous les X jours par média (0 = jamais)
    "enquete_hour": 9,            # 1er média à cette heure, puis +1 h par média (moins de saturation de Gemini le matin)          # dernier recours : photo de l'article (droits NON garantis)
    "carousel_size": [1080, 1350],
    "keep_days": 7,
    "medias": {},                 # personnalisation : {id: {name, handle, color, cta, enabled}}
}

_lock = threading.Lock()


def load_settings() -> dict:
    s = copy.deepcopy(DEFAULT_SETTINGS)
    if SETTINGS_FILE.exists():
        try:
            s.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
        except Exception:
            logging.getLogger("studio").warning("settings.json illisible, réglages par défaut")
    if CLOUD:
        _cloud_overlay(s)
    elif not s.get("gemini_key"):
        s["gemini_key"] = os.environ.get("GEMINI_API_KEY", "")
    return s


def _mask(value: str) -> None:
    """Cache une valeur dans les journaux publics de GitHub Actions."""
    if value and value not in _MASKED and os.environ.get("GITHUB_ACTIONS") == "true":
        _MASKED.add(value)
        print(f"::add-mask::{value}", flush=True)


def _fernet(seed: str):
    from cryptography.fernet import Fernet

    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(("studio-ig:" + seed).encode()).digest()))


def _cloud_overlay(s: dict) -> None:
    env = lambda k: (os.environ.get(k) or "").strip()
    for k, e in _ENV_KEYS.items():
        if env(e):
            s[k] = env(e)
    if not s.get("ntfy_topic"):
        s["notify"] = False                      # pas de sujet ntfy fourni : pas de notifications
    if env("BUFFER_HUB_X"):
        s["hub"] = {**(s.get("hub") or {}), "enabled": True, "x": env("BUFFER_HUB_X")}
    try:
        vault = json.loads(VAULT.read_text(encoding="utf-8")) if VAULT.exists() else {}
    except Exception:
        vault = {}
    for mid, c in (s.get("publish") or {}).items():
        M = mid.upper()
        for k, e in (("ig_user_id", f"IG_{M}_USER"), ("x_token", f"X_{M}_TOKEN"), ("x_secret", f"X_{M}_SECRET"),
                     ("x", f"BUFFER_{M}_X"), ("tiktok", f"BUFFER_{M}_TIKTOK"), ("instagram", f"BUFFER_{M}_INSTAGRAM")):
            if env(e):
                c[k] = env(e)
        base = env(f"IG_{M}_TOKEN")
        if not base:
            continue
        c["ig_token"] = base
        v = vault.get(mid)
        if v:
            try:
                c["ig_token"] = _fernet(base).decrypt(v["t"].encode()).decode()
                c["ig_refreshed"] = v.get("at", time.time())
                _mask(c["ig_token"])
                continue
            except Exception:                    # nouveau jeton mis dans les secrets : on repart de celui-là
                c["ig_refreshed"] = time.time() - 15 * 86400
        c.setdefault("ig_refreshed", time.time() - 15 * 86400)


def _cloud_strip(s: dict) -> dict:
    """Copie sans aucune clé, à écrire sur le disque. Les jetons Instagram prolongés partent chiffrés dans VAULT."""
    out = copy.deepcopy(s)
    for k in _SECRET_KEYS:
        out.pop(k, None)
    vault = {}
    for mid, c in (out.get("publish") or {}).items():
        base = (os.environ.get(f"IG_{mid.upper()}_TOKEN") or "").strip()
        tok = c.get("ig_token", "")
        if base and tok and tok != base:
            _mask(tok)
            vault[mid] = {"t": _fernet(base).encrypt(tok.encode()).decode(), "at": c.get("ig_refreshed", time.time())}
        for k in _PUB_SECRET_KEYS:
            c.pop(k, None)
    VAULT.write_text(json.dumps(vault), encoding="utf-8")
    return out


def save_settings(updates: dict) -> dict:
    with _lock:
        s = load_settings()
        for k, v in updates.items():
            if k == "medias" and isinstance(v, dict):
                for mid, fields in v.items():
                    s["medias"].setdefault(mid, {}).update(fields)
            elif k in DEFAULT_SETTINGS:
                s[k] = v
        DATA.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(_cloud_strip(s) if CLOUD else s, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
        return s


def load_medias(settings: dict | None = None) -> tuple[list[dict], list[str]]:
    """Retourne (médias avec personnalisation appliquée, mots bloqués communs)."""
    settings = settings or load_settings()
    with open(ROOT / "medias.yaml", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    medias = []
    for m in raw["medias"]:
        m = {**m, "enabled": True, **settings.get("medias", {}).get(m["id"], {})}
        medias.append(m)
    return medias, raw.get("common_blocked", [])


def get_media(media_id: str, settings: dict | None = None) -> dict | None:
    return next((m for m in load_medias(settings)[0] if m["id"] == media_id), None)


def mask(key: str) -> str:
    return f"…{key[-4:]}" if key and len(key) > 8 else ("enregistrée" if key else "")


class RingHandler(logging.Handler):
    """Garde les derniers messages pour les afficher dans le site."""

    def __init__(self, size: int = 200):
        super().__init__()
        self.lines: deque = deque(maxlen=size)

    def emit(self, record):
        self.lines.append({"t": record.created, "lvl": record.levelname, "msg": record.getMessage()})


RING = RingHandler()


def setup_logging() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    fh = logging.FileHandler(DATA / "studio.log", encoding="utf-8")
    fh.setFormatter(fmt)
    handlers = [fh, RING]
    if sys.stdout is not None:              # lancé sans console (démarrage avec Windows) : pas de sortie écran
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        handlers.append(sh)
    for h in handlers:
        root.addHandler(h)
    for noisy in ("urllib3", "PIL", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
