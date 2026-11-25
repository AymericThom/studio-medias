"""Récupération des flux RSS des médias français."""
from __future__ import annotations

import calendar
import concurrent.futures as cf
import hashlib
import html
import logging
import re
import time

import feedparser
import requests

from .config import USER_AGENT

log = logging.getLogger("media.sources")

# Préfixes éditoriaux à retirer des titres ("DIRECT.", "VIDÉO -", "INFO FRANCEINFO.", ...)
PREFIX_RE = re.compile(
    r"^\s*(?:🔴\s*)?(?:EN\s+DIRECT|DIRECT|LIVE|VID[ÉE]O|PHOTOS?|INFO\s+[A-Z0-9ÉÈ' ]{2,25}|INFOGRAPHIE|CARTE|"
    r"R[ÉE]CIT|ENQU[ÊE]TE|T[ÉE]MOIGNAGE|INTERVIEW|ENTRETIEN|EXCLUSIF|ANALYSE|D[ÉE]CRYPTAGE|REPORTAGE|"
    r"POINT DE VUE|FACT[- ]CHECK|VRAI OU FAUX|ALERTE)\s*[\.:\-–—|]\s*",
    re.IGNORECASE,
)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def clean_text(text: str) -> str:
    text = html.unescape(TAG_RE.sub(" ", text or ""))
    return WS_RE.sub(" ", text.replace("\xa0", " ")).strip()


def clean_title(title: str) -> tuple[str, str]:
    """Retourne (titre nettoyé, préfixe retiré en minuscules)."""
    t = clean_text(title)
    prefix = ""
    for _ in range(2):
        m = PREFIX_RE.match(t)
        if not m:
            break
        prefix += m.group(0).lower()
        t = t[m.end():]
    return t.strip(" -–—"), prefix


def _entry_time(e) -> float | None:
    for key in ("published_parsed", "updated_parsed"):
        st = e.get(key)
        if st:
            try:
                return float(calendar.timegm(st))
            except Exception:
                pass
    return None


IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"', re.I)


def _entry_image(e) -> str:
    """URL de l'image de l'article fournie par le flux RSS (media:content, enclosure, <img>)."""
    for key in ("media_content", "media_thumbnail"):
        for m in e.get(key, []) or []:
            url = m.get("url", "")
            if url and not url.lower().endswith((".mp4", ".mp3", ".svg")):
                return url
    for enc in e.get("enclosures", []) or []:
        if str(enc.get("type", "")).startswith("image") and enc.get("href"):
            return enc["href"]
    m = IMG_RE.search(e.get("summary", "") or e.get("content", [{}])[0].get("value", "") if e.get("content") else e.get("summary", ""))
    return m.group(1) if m else ""


def fetch_feed(feed: dict, timeout: int = 15) -> list[dict]:
    now = time.time()
    try:
        r = requests.get(feed["url"], headers={"User-Agent": USER_AGENT}, timeout=timeout)
        r.raise_for_status()
        parsed = feedparser.parse(r.content)
    except Exception as ex:
        log.warning("Flux indisponible %s : %s", feed["name"], ex)
        return []
    out = []
    for e in parsed.entries[:80]:
        raw_title = e.get("title", "")
        if not raw_title:
            continue
        source = feed["name"]
        if feed.get("aggregator") and " - " in raw_title:
            raw_title, source = raw_title.rsplit(" - ", 1)
            source = source.strip()
        title, prefix = clean_title(raw_title)
        if len(title) < 15:
            continue
        summary = clean_text(e.get("summary", "") or e.get("description", ""))
        if feed.get("aggregator"):
            summary = ""  # le résumé Google News répète juste les titres
        if summary.lower().startswith(title.lower()[:40]):
            summary = summary[len(title):].strip(" .-")
        link = e.get("link", "")
        dated = _entry_time(e)
        published = dated or now
        if published > now + 600:  # dates dans le futur = flux mal daté
            published, dated = now, None
        out.append({
            "id": hashlib.sha1((link or source + title).encode("utf-8")).hexdigest()[:16],
            "source": source,
            "title": title,
            "summary": summary[:500],
            "link": link,
            "published": published,
            "fetched": now,
            "weight": float(feed.get("weight", 1.0)),
            "trusted": 1 if feed.get("trusted") else 0,
            "dated": 1 if dated else 0,
            "image": "" if feed.get("aggregator") else _entry_image(e),
            "_prefix": prefix,
        })
    return out


def fetch_all(feeds: list[dict]) -> list[dict]:
    articles: list[dict] = []
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        for items in ex.map(fetch_feed, feeds):
            articles.extend(items)
    # dédoublonnage par id (même lien présent dans 2 flux)
    seen, unique = set(), []
    for a in articles:
        if a["id"] not in seen:
            seen.add(a["id"])
            a.pop("_prefix", None)
            unique.append(a)
    log.info("%d articles récupérés depuis %d flux", len(unique), len(feeds))
    return unique
