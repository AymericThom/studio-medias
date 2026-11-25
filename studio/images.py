"""Photos LIBRES DE DROITS uniquement (crédit affiché automatiquement).

1. Wikipédia / Wikimedia Commons : personnalités, lieux, institutions (licences CC / domaine public)
2. Pexels (clé gratuite, optionnelle) : photos d'illustration
Jamais les photos des articles de presse (droits d'auteur).
Cache local (data/cache) : une personnalité déjà illustrée n'est pas redemandée.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import time
import unicodedata

import requests
from PIL import Image

from . import db
from .config import DATA

log = logging.getLogger("studio.images")
HEADERS = {"User-Agent": "StudioMedias/1.0 (outil personnel de veille d'actualite; python-requests)"}
OK_LICENSES = ("cc0", "public domain", "domaine public", "pd", "cc by", "cc-by")
BAD_LICENSES = ("nc", "nd", "fair use", "non-free")
CACHE = DATA / "cache"
_cooldown_until = 0.0
_last_call = 0.0
_wiki_lock = __import__("threading").Lock()


SAFE_QUALIFIERS = {"france", "entreprise", "societe", "homme politique", "femme politique", "personnalite politique",
                   "footballeur", "football", "basket-ball", "basketteur", "joueur de tennis", "joueuse de tennis",
                   "pilote", "pilote automobile", "rugby a xv", "journaliste", "institution", "parti politique",
                   "club", "ville", "pays", "organisation", "constructeur automobile"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    # "Assemblée nationale (France)" -> "assemblee nationale", mais "Orange (Vaucluse)" reste distinct de "Orange"
    s = re.sub(r"\s*\(([^)]*)\)\s*", lambda m: " " if m.group(1).strip() in SAFE_QUALIFIERS else f" {m.group(1)} ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _same_subject(subject: str, title: str) -> bool:
    """Évite LA pire erreur : illustrer une info avec la photo d'une autre personne."""
    a, b = _norm(subject), _norm(title)
    if not a or not b:
        return False
    if a == b:
        return True
    ta, tb = a.split(), b.split()
    return set(ta) <= set(tb) and len(tb) - len(ta) <= 1 and tb[-1] == ta[-1]


def _get(url: str, **kw):
    """GET poli envers Wikimedia : requêtes espacées, pause automatique si limite atteinte."""
    global _cooldown_until, _last_call
    wiki = "wiki" in url
    if wiki and time.time() < _cooldown_until:
        return None
    with _wiki_lock if wiki else _NullLock():
        if wiki:
            wait = 3.0 - (time.time() - _last_call)
            if wait > 0:
                time.sleep(wait)
            _last_call = time.time()
        r = requests.get(url, headers=HEADERS, timeout=20, **kw)
    if r.status_code == 429:
        _cooldown_until = time.time() + 10 * 60
        log.warning("Wikimedia limite les requêtes : pause des photos Wikipédia pendant 10 min (le studio réessaiera tout seul)")
        return None
    return r


class _NullLock:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _download(url: str, min_w: int = 500, min_h: int = 350) -> Image.Image | None:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (hashlib.sha1(url.encode()).hexdigest()[:20] + ".jpg")
    try:
        if path.exists():
            img = Image.open(path).convert("RGB")
            return img if img.width >= min_w and img.height >= min_h else None
        r = _get(url)
        if r is None or r.status_code != 200 or not r.headers.get("Content-Type", "").startswith("image/"):
            return None
        img = Image.open(io.BytesIO(r.content))
        img.load()
        img = img.convert("RGB")
        if img.width < 300 or img.height < 200:
            return None
        img.save(path, "JPEG", quality=92)
        return img if img.width >= min_w and img.height >= min_h else None
    except Exception as ex:
        log.debug("Téléchargement image échoué %s : %s", url, ex)
        return None


def _commons_info(filename: str) -> tuple[str, str] | None:
    """(url miniature 1600 px, crédit) si la licence est libre."""
    r = _get("https://commons.wikimedia.org/w/api.php", params={
        "action": "query", "format": "json", "formatversion": 2, "titles": f"File:{filename}",
        "prop": "imageinfo", "iiprop": "url|extmetadata|mime", "iiurlwidth": 1280})
    try:
        info = r.json()["query"]["pages"][0]["imageinfo"][0]
    except Exception:
        return None
    if info.get("mime") not in ("image/jpeg", "image/png", "image/webp"):
        return None
    meta = info.get("extmetadata", {})
    lic = meta.get("LicenseShortName", {}).get("value", "")
    low = lic.lower()
    if not any(k in low for k in OK_LICENSES) or any(re.search(rf"\b{k}\b", low) for k in BAD_LICENSES):
        return None
    artist = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", ""))).strip()[:40]
    return info.get("thumburl") or info["url"], f"{artist or 'Wikimedia Commons'} / {lic}"


def from_wikipedia(subject: str) -> tuple[Image.Image, str] | None:
    if not subject:
        return None
    key = "wiki:" + _norm(subject)
    cached = db.kv_get(key)
    if cached:
        c = json.loads(cached)
        if c.get("url") and time.time() - c["t"] < 30 * 86400:
            img = _download(c["url"])
            return (img, c["credit"], {"title": c.get("title", subject), "description": c.get("desc", "")}) if img else None
        if not c.get("url") and time.time() - c["t"] < 86400:   # "pas de photo libre" mémorisé 24 h
            return None
    r = _get("https://fr.wikipedia.org/w/api.php", params={
        "action": "query", "format": "json", "formatversion": 2, "redirects": 1,
        "generator": "search", "gsrsearch": subject, "gsrlimit": 5,
        "prop": "pageimages|description", "piprop": "name", "pilicense": "free"})
    if r is None:
        return None
    try:
        pages = sorted(r.json().get("query", {}).get("pages", []), key=lambda p: p.get("index", 99))
    except Exception:
        return None
    pages = [p for p in pages if _same_subject(subject, p.get("title", ""))][:1]
    result = None
    for p in pages:
        name = p.get("pageimage")
        if not name or name.lower().endswith((".svg", ".gif")):
            continue
        info = _commons_info(name)
        if info:
            img = _download(info[0])
            if img:
                meta = {"title": p.get("title", subject), "description": p.get("description", "")}
                result = (img, info[1], meta)
                db.kv_set(key, json.dumps({"url": info[0], "credit": info[1], "t": time.time(),
                                           "title": meta["title"], "desc": meta["description"]}))
                log.info("Photo Wikipédia pour « %s » (%s)", subject, info[1])
    if result is None and time.time() >= _cooldown_until:
        db.kv_set(key, json.dumps({"url": None, "t": time.time()}))
    return result


def from_commons_search(query: str) -> tuple[Image.Image, str] | None:
    """Photo d'illustration générique (ex. « euro banknotes ») sur Wikimedia Commons, licence libre."""
    if not query:
        return None
    key = "commons:" + _norm(query)
    cached = db.kv_get(key)
    if cached:
        c = json.loads(cached)
        if time.time() - c["t"] < 7 * 86400:
            if not c.get("url"):
                return None
            img = _download(c["url"])
            return (img, c["credit"]) if img else None
    r = _get("https://commons.wikimedia.org/w/api.php", params={
        "action": "query", "format": "json", "formatversion": 2, "list": "search", "srnamespace": 6,
        "srsearch": f"{query} filetype:bitmap", "srlimit": 8})
    if r is None:
        return None
    try:
        hits = r.json().get("query", {}).get("search", [])
    except Exception:
        return None
    keywords = [w for w in _norm(query).split() if len(w) >= 4]
    for h in hits:
        name = h.get("title", "").removeprefix("File:")
        if not name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            continue
        if keywords and not any(k in _norm(name) for k in keywords):   # nom de fichier sans rapport : on passe
            continue
        info = _commons_info(name)
        if not info:
            continue
        img = _download(info[0])
        if img and img.width >= 900:
            db.kv_set(key, json.dumps({"url": info[0], "credit": info[1], "t": time.time()}))
            log.info("Photo d'illustration Commons pour « %s » (%s)", query, info[1])
            return img, info[1]
    if time.time() >= _cooldown_until:
        db.kv_set(key, json.dumps({"url": None, "t": time.time()}))
    return None


def from_pexels(query: str, key: str) -> tuple[Image.Image, str] | None:
    if not key or not query:
        return None
    try:
        r = requests.get("https://api.pexels.com/v1/search", timeout=15, headers={"Authorization": key},
                         params={"query": query, "per_page": 6, "orientation": "landscape"})
        photos = r.json().get("photos", [])
    except Exception as ex:
        log.debug("Pexels indisponible : %s", ex)
        return None
    for ph in photos:
        img = _download(ph["src"].get("large2x") or ph["src"]["large"])
        if img:
            return img, f"{ph.get('photographer', 'Pexels')[:30]} / Pexels"
    return None


def from_openverse(query: str) -> tuple[Image.Image, str] | None:
    """Openverse (WordPress) : des millions de photos sous licence libre, sans clé."""
    if not query:
        return None
    key = "openverse:" + _norm(query)
    cached = db.kv_get(key)
    if cached:
        c = json.loads(cached)
        if time.time() - c["t"] < 7 * 86400:
            img = _download(c["url"]) if c.get("url") else None
            return (img, c["credit"]) if img else None
    try:
        r = requests.get("https://api.openverse.org/v1/images/", headers=HEADERS, timeout=20, params={
            "q": query, "license_type": "commercial,modification", "page_size": 15, "mature": "false"})
        results = r.json().get("results", []) if r.status_code == 200 else []
    except Exception:
        results = []
    keywords = [w for w in _norm(query).split() if len(w) >= 4]
    for res in results:
        if (res.get("width") or 0) < 1000 or str(res.get("url", "")).lower().endswith(".gif"):
            continue
        hay = _norm(res.get("title", "") + " " + " ".join(t.get("name", "") for t in res.get("tags") or []))
        if keywords and not any(k in hay for k in keywords):
            continue
        img = _download(res["url"], 900, 500)
        if img:
            lic = str(res.get("license", "")).lower()
            lic_txt = {"cc0": "CC0", "pdm": "Domaine public"}.get(lic, f"CC {lic.upper()} {res.get('license_version') or ''}".strip())
            credit = f"{(res.get('creator') or res.get('provider') or 'Openverse')[:30]} / {lic_txt}"
            db.kv_set(key, json.dumps({"url": res["url"], "credit": credit, "t": time.time()}))
            log.info("Photo libre Openverse pour « %s » (%s)", query, credit)
            return img, credit
    db.kv_set(key, json.dumps({"url": None, "t": time.time()}))
    return None


OG_RE = re.compile(r"""<meta[^>]+(?:property|name)=["'](?:og:image|twitter:image)["'][^>]+content=["']([^"']+)""", re.I)
OG_RE2 = re.compile(r"""<meta[^>]+content=["']([^"']+)["'][^>]+(?:property|name)=["'](?:og:image|twitter:image)""", re.I)


def _og_image(link: str) -> str:
    if not link or "news.google." in link:
        return ""
    try:
        r = requests.get(link, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0"}, timeout=12)
        m = OG_RE.search(r.text[:200_000]) or OG_RE2.search(r.text[:200_000])
        return m.group(1).replace("&amp;", "&") if m else ""
    except Exception:
        return ""


def from_articles(articles: list[dict]) -> tuple[Image.Image, str] | None:
    """Dernier recours : photo de l'article de presse (droits NON garantis), créditée au média."""
    arts = [a for a in sorted(articles, key=lambda a: -a.get("weight", 1)) if "news.google." not in a.get("link", "")][:4]
    for min_w in (900, 600):
        for a in arts:
            for url in (a.get("image") or "", ""):
                if not url:
                    url = _og_image(a.get("link", ""))
                if not url:
                    continue
                img = _download(url, min_w, int(min_w * 0.5))
                if img:
                    log.info("Photo de l'article (%s) utilisée en dernier recours", a["source"])
                    return img, f"© {a['source']}"
    return None


def wiki_paused() -> bool:
    return time.time() < _cooldown_until


def find_images(subjects: list[str], query_en: str = "", pexels_key: str = "", articles: list[dict] | None = None,
                allow_press: bool = True, skip_wiki: bool = False) -> tuple[list[tuple], str]:
    """Retourne (photos, type). Ordre : Wikipédia (la vraie personne / le vrai lieu) -> photo de l'article
    (si autorisé) -> photo d'illustration libre (Pexels, Openverse, Commons). Type : wiki / press / stock / none."""
    found, seen = [], set()
    for subj in ([] if skip_wiki else [s for s in subjects if s][:2]):
        res = from_wikipedia(subj)
        if res and res[1] not in seen:
            found.append(res)
            seen.add(res[1])
    if found:
        return found, "wiki"
    if allow_press and articles:
        res = from_articles(articles)
        if res:
            return [res], "press"
    res = from_pexels(query_en, pexels_key) or from_openverse(query_en) or from_commons_search(query_en)
    if res:
        return [res], "stock"
    return [], "none"
