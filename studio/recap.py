"""« L'essentiel du jour » : chaque soir, un carrousel récapitulatif par média (format phare des comptes d'actu).

Aucun appel à l'IA : le récap reprend uniquement les posts du jour DÉJÀ vérifiés (✅ ou ✏️), avec leur texte vérifié.
Couverture (mosaïque des photos du jour) + 1 image par info + image d'abonnement, tweet récapitulatif, description.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from . import db
from .config import POSTS, TIMEZONE

log = logging.getLogger("studio.recap")
TZ = ZoneInfo(TIMEZONE)
DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre",
          "décembre"]
NUM = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
_PREFIX = re.compile(r"^[^\wÀ-ÿ]*(?:FLASH|ALERTE|OFFICIEL|INFO|DERNIÈRE MINUTE)\s*[-–—:]\s*", re.I)
_VIA = re.compile(r"\s*\((?:via|selon)\s[^)]*\)\s*\.?\s*$", re.I)


def clean_item(x_text: str) -> str:
    """« 🇫🇷 FLASH - Le texte… (via Le Monde). » -> « Le texte… »"""
    t = _VIA.sub("", _PREFIX.sub("", (x_text or "").strip())).strip()
    return t if t.endswith((".", "!", "?", "…")) else t + "."


def date_fr(dt: datetime) -> str:
    return f"{DAYS[dt.weekday()]} {dt.day} {MONTHS[dt.month - 1]}"


def photo_path(d: dict) -> str:
    """La photo d'origine du post (photo.jpg) ; à défaut, l'image X recadrée."""
    for rel in (d.get("photo"), d.get("x_image")):
        if rel and (POSTS / rel).exists():
            return str(POSTS / rel)
    return ""


def pick_items(media_id: str, s: dict, since: float) -> list[dict]:
    out = []
    for p in db.posts(media_id, since):
        d = p["data"]
        if (p["hidden"] or d.get("kind") in ("recap", "enquete") or (d.get("verif") or {}).get("verdict") not in ("ok", "corrige")
                or (p["sensitive"] and not s.get("auto_sensitive", False))):
            continue
        out.append(p)
    out.sort(key=lambda p: (-p["importance"], -p["created"]))
    return out[:5]


def make_recap(media: dict, s: dict) -> bool:
    from .engine import files_rel, slug, with_tiktok
    from .visuals import render_recap

    now = datetime.now(TZ)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    posts = pick_items(media["id"], s, midnight)
    if len(posts) < 3:
        log.info("[%s] récap du jour : pas assez de posts vérifiés (%d)", media["name"], len(posts))
        return False
    items = [{"text": clean_item(p["data"].get("x_text", "")), "label": p["data"].get("label", ""),
              "emoji": p["data"].get("label_emoji", ""), "credit": (p["data"].get("credits") or [""])[0],
              "photo": photo_path(p["data"]),
              # ancien post sans photo d'origine, image X à 2 photos côte à côte : on garde la 1re
              "crop_left": not p["data"].get("photo") and len(p["data"].get("credits") or []) >= 2} for p in posts]
    date_txt = date_fr(now)
    out = POSTS / media["id"] / now.strftime("%Y-%m-%d") / f"{now.strftime('%H%M%S')}_{slug('essentiel-du-jour')}"
    files = with_tiktok(render_recap(media, items, date_txt, out, s.get("carousel_size", [1080, 1350])), out)

    head = f"📰 L'ESSENTIEL DU JOUR · {date_txt}\n"
    lines = []
    for p in posts:                                     # tweet : autant de titres que la limite de 280 le permet
        cand = head + "\n".join(lines + [f"▪️ {p['headline']}"])
        if len(cand) > 275:
            break
        lines.append(f"▪️ {p['headline']}")
    x_text = head + "\n".join(lines)
    sources = sorted({src for p in posts for src in p["data"].get("sources", [])})[:6]
    tags = ["#actu", "#info"] + [h for p in posts for h in p["data"].get("hashtags", [])][:3]
    caption = (f"L'essentiel du jour en {len(items)} infos 👇\n\n"
               + "\n\n".join(f"{NUM[i]} {it['text']}" for i, it in enumerate(items))
               + "\n\nQuelle info t'a le plus marqué aujourd'hui ?"
               + (f"\n\nSources : {', '.join(sources)}" if sources else "")
               + "\n\n" + " ".join(dict.fromkeys(tags)))
    tiktok_text = (f"L'essentiel du jour en {len(items)} infos ({date_txt}) 👇\n\n"
                   + "\n".join(f"{NUM[i]} {p['headline']}" for i, p in enumerate(posts)) + "\n\n" + " ".join(dict.fromkeys(tags)))
    data = {
        "kind": "recap", "x_text": x_text, "caption": caption, "caption_base": caption, "tiktok_text": tiktok_text,
        "hashtags": list(dict.fromkeys(tags)), "label": "L'ESSENTIEL DU JOUR", "label_emoji": "📰",
        "sources": sources, "credits": [], "press": False, "photo_kind": "recap", "articles": [],
        "news_time": max(p["created"] for p in posts), "items": [p["id"] for p in posts],
        "verif": {"verdict": "ok", "problemes": [], "textes": [f"Reprise de {len(posts)} posts déjà vérifiés"]},
        "dir": out.relative_to(POSTS).as_posix(), "rev": 1, **files_rel(files),
    }
    db.add_post(media["id"], f"L'essentiel du jour · {date_txt}", 9, False, len(posts), data)
    log.info("[%s] récap du jour prêt (%d infos)", media["name"], len(posts))
    return True


def recap_due(media_id: str, s: dict) -> bool:
    now = datetime.now(TZ)
    return (s.get("recap", True) and s.get("recap_hour", 19) <= now.hour < 23
            and not db.kv_get(f"recap:{media_id}:{now.strftime('%Y-%m-%d')}")
            and time.time() - float(db.kv_get(f"recap_retry:{media_id}", 0)) > 3600)


def run_recaps(medias: list[dict], s: dict) -> None:
    for m in medias:
        if m.get("enabled", True) and recap_due(m["id"], s):
            try:
                ok = make_recap(m, s)
            except Exception:
                log.exception("[%s] récap du jour impossible", m["name"])
                ok = False
            if ok:
                db.kv_set(f"recap:{m['id']}:{datetime.now(TZ).strftime('%Y-%m-%d')}", "ok")
            else:                       # pas assez de posts vérifiés : nouvel essai dans 1 h (jusqu'à 22 h)
                db.kv_set(f"recap_retry:{m['id']}", time.time())
