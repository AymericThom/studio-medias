"""Récupère le TEXTE COMPLET des articles (pas seulement le résumé RSS) pour vérifier les faits.

Méthode : 1) le champ « articleBody » des données structurées (JSON-LD) que publient la plupart des médias,
2) sinon les paragraphes <p> de la page. Les liens Google News (redirections) sont ignorés.
Les articles réservés aux abonnés ne donnent souvent que le début : on combine donc plusieurs médias.
"""
from __future__ import annotations

import concurrent.futures as cf
import html
import json
import logging
import re

import requests

log = logging.getLogger("studio.fulltext")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "fr-FR,fr;q=0.9"}
LD_RE = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)
P_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")
JUNK = ("abonnez-vous", "abonné", "newsletter", "cookies", "javascript", "publicité", "lire aussi", "à lire aussi",
        "inscrivez-vous", "téléchargez l'application", "tous droits réservés", "partager sur", "votre navigateur")


def _clean(t: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", t or ""))).strip()


def _from_jsonld(page: str) -> str:
    best = ""
    for block in LD_RE.findall(page):
        try:
            data = json.loads(block.strip())
        except Exception:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop()
            if isinstance(d, dict):
                body = d.get("articleBody")
                if isinstance(body, str) and len(body) > len(best):
                    best = body
                stack.extend(v for v in d.values() if isinstance(v, (dict, list)))
            elif isinstance(d, list):
                stack.extend(d)
    return _clean(best)


def _from_paragraphs(page: str) -> str:
    m = re.search(r"<article\b.*?</article>", page, re.S | re.I)
    zone = m.group(0) if m and len(m.group(0)) > 2000 else page
    parts = []
    for p in P_RE.findall(zone):
        t = _clean(p)
        if len(t) >= 60 and not any(j in t.lower() for j in JUNK):
            parts.append(t)
    return " ".join(parts)


def fetch_text(url: str, limit: int = 6000) -> str:
    if not url or "news.google." in url:
        return ""
    try:
        r = requests.get(url, headers=UA, timeout=12)
        ctype = r.headers.get("Content-Type", "")
        if r.status_code != 200 or "html" not in ctype:
            return ""
        if "charset" not in ctype.lower():          # sinon accents cassés (« AprÃ¨s »)
            r.encoding = "utf-8"
        page = r.text
    except Exception:
        return ""
    text = _from_jsonld(page)
    if '"@context"' in text or "schema.org" in text:   # champ pollué par du code
        text = ""
    if len(text) < 400:
        alt = _from_paragraphs(page)
        if len(alt) > len(text):
            text = alt
    return text[:limit] if len(text) >= 300 else ""


def fetch_cluster_texts(articles: list[dict], max_articles: int = 4, use_browser: bool = True) -> list[dict]:
    """Textes complets des meilleurs articles d'un sujet, de médias différents.
    1) lecture simple (rapide) ; 2) pour les sites qui bloquent les robots : vrai navigateur (Chrome/Edge)."""
    seen_sources, picked = set(), []
    for a in sorted(articles, key=lambda a: -a.get("weight", 1)):
        if "news.google." in a.get("link", "") or a["source"] in seen_sources:
            continue
        seen_sources.add(a["source"])
        picked.append(a)
        if len(picked) >= max_articles + 2:
            break
    with cf.ThreadPoolExecutor(6) as ex:
        texts = list(ex.map(lambda a: fetch_text(a.get("link", "")), picked))
    n_simple = sum(1 for t in texts if t)
    missing = [i for i, t in enumerate(texts) if not t]
    n_browser = 0
    if use_browser and missing and n_simple < max_articles:
        from .browser import PageReader

        with PageReader() as reader:
            for i in missing[: max_articles - n_simple + 1]:
                texts[i] = reader.read(picked[i].get("link", ""))
                n_browser += bool(texts[i])
    out = [{"source": a["source"], "title": a.get("title", ""), "text": t} for a, t in zip(picked, texts) if t]
    log.info("Vérification : %d article(s) complet(s) lu(s) (%d direct, %d via navigateur) sur %d",
             len(out[:max_articles]), n_simple, n_browser, len(picked))
    return out[:max_articles]
