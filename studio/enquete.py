"""Enquêtes automatiques : un dossier de fond vérifié, tous les quelques jours, pour chaque média.

Ce n'est pas du journalisme de terrain (pas d'interview, pas de document exclusif) : c'est une ENQUÊTE DOCUMENTAIRE.
Le studio repère l'affaire la plus suivie de la semaine dans la niche, lit les articles complets de plusieurs
médias, reconstitue la chronologie, les chiffres, les acteurs, les points de désaccord et ce qu'on ne sait pas encore,
puis fait vérifier chaque affirmation par une seconde passe avant de créer un carrousel « 🔎 L'ENQUÊTE ».
"""
from __future__ import annotations

import json
import logging
import time
import zipfile
from datetime import datetime
from pathlib import Path

from . import db
from .ai import CHARTE, VERIF_SYSTEM, AIError, Gemini, _age
from .cluster import cluster_articles, score_clusters
from .fulltext import fetch_text
from .humanize import STYLE, humanize
from .visuals import slide_cover, slide_cta, slide_points, x_image

log = logging.getLogger("studio.enquete")


def pick_topic(media: dict, blocked: list[str]) -> dict | None:
    """L'affaire de fond : beaucoup d'articles, plusieurs médias, sur plusieurs jours, encore active."""
    now = time.time()
    arts = db.recent_articles(media["id"], 7 * 24)
    past = json.loads(db.kv_get(f"enq_done:{media['id']}", "[]"))
    clusters, extra = cluster_articles(arts, 0.28, [x["t"] for x in past if now - x["ts"] < 21 * 86400])
    cfg = {"editorial": {"boost_keywords": [], "blocked_keywords": blocked}}
    ranked = score_clusters(clusters, cfg, {"item": set()}, {"item": extra})
    best, best_score = None, 0
    for c in ranked:
        days = {time.strftime("%Y-%m-%d", time.localtime(a["published"])) for a in c["articles"]}
        if c["n_sources"] < 3 or len(c["articles"]) < 6 or c["latest"] < now - 48 * 3600:
            continue
        score = len(c["articles"]) * (1 + 0.6 * (len(days) - 1)) * (1 + 0.15 * c["n_sources"])
        if score > best_score:
            best, best_score = c, score
    return best


def _texts(c: dict, n: int = 5, use_browser: bool = True) -> list[dict]:
    """Textes complets de n articles variés (médias et dates différents) ; vrai navigateur en secours."""
    cands, seen = [], set()
    for a in sorted(c["articles"], key=lambda a: (-a["weight"], -a["published"])):
        key = (a["source"], time.strftime("%d", time.localtime(a["published"])))
        if "news.google." in a.get("link", "") or key in seen:
            continue
        seen.add(key)
        cands.append(a)
        if len(cands) >= n * 2:
            break
    picked, failed = [], []
    for a in cands:
        t = fetch_text(a.get("link", ""))
        (picked if t else failed).append((a, t))
        if len(picked) >= n:
            break
    if use_browser and len(picked) < n and failed:
        from .browser import PageReader

        with PageReader() as reader:
            for a, _ in failed[: n - len(picked)]:
                t = reader.read(a.get("link", ""))
                if t:
                    picked.append((a, t))
    return [{"source": a["source"], "title": a["title"], "date": time.strftime("%d/%m", time.localtime(a["published"])),
             "text": t} for a, t in picked[:n]]


def write_enquete(gem: Gemini, media: dict, c: dict, texts: list[dict]) -> dict:
    docs = "\n\n".join(f"=== {t['source']}, {t['date']} : {t['title']}\n{t['text'][:3200]}" for t in texts)
    titles = "\n".join(f"- {a['source']} ({_age(a['published'])}) : {a['title']}" for a in
                       sorted(c["articles"], key=lambda a: a["published"])[-25:])
    system = f"""Tu es le journaliste « enquête » de « {media['name']} », média spécialisé dans {media['niche']}.
Tu écris L'ENQUÊTE : un dossier de fond qui fait comprendre une affaire en profondeur, à partir UNIQUEMENT des documents fournis.
{CHARTE}
{STYLE}"""
    prompt = f"""TOUS LES TITRES SUR CETTE AFFAIRE (chronologique) :
{titles}

ARTICLES COMPLETS :
{docs}

Rédige le dossier en JSON :
{{"headline": "titre interne ≤ 90 caractères",
 "cover_text": "phrase d'accroche de la couverture, 25 à 40 mots : l'affaire et pourquoi elle compte",
 "sections": [
   {{"title": "Ce qui s'est passé ⬇️", "points": ["chronologie : 3 à 5 étapes datées, 6 à 20 mots chacune, mots clés en **gras**"]}},
   {{"title": "Les chiffres clés", "points": ["3 à 5 chiffres précis tirés des articles"]}},
   {{"title": "Qui est impliqué", "points": ["3 à 5 acteurs et leur rôle"]}},
   {{"title": "Ce qui fait débat", "points": ["2 à 4 positions opposées, attribuées"]}},
   {{"title": "Ce qu'on ne sait pas encore", "points": ["2 à 4 questions ouvertes ou prochaines étapes"]}}
 ],
 "caption": "description complète, 250 à 400 mots, paragraphes courts séparés par une ligne vide, ton de journaliste qui raconte",
 "x_thread": ["1/ ... (le premier tweet résume l'affaire, ≤ 270 caractères)", "2/ ...", "3/ ...", "4/ ...", "5/ ..."],
 "hashtags": ["3 à 5"],
 "image_subjects": ["personne, lieu ou organisation au cœur de l'affaire, titre exact de sa page Wikipédia en français"],
 "image_query_en": "2 à 4 mots en anglais pour une photo d'illustration",
 "sensitive": true/false}}
Si une section n'a pas assez de faits sourcés, retire-la plutôt que d'inventer (minimum 3 sections)."""
    data = gem.call(system, prompt, temperature=0.4)
    if not isinstance(data, dict) or not data.get("sections"):
        raise AIError("Dossier d'enquête illisible")
    return data


def verify_enquete(gem: Gemini, draft: dict, texts: list[dict], photo_info: str = "") -> dict:
    docs = "\n\n".join(f"=== {t['source']}, {t['date']} : {t['title']}\n{t['text'][:3200]}" for t in texts)
    body = {k: draft.get(k) for k in ("cover_text", "sections", "caption", "x_thread")}
    prompt = (f"ARTICLES :\n{docs}\n\nDOSSIER À VÉRIFIER (JSON) :\n{json.dumps(body, ensure_ascii=False)}\n\n"
              f"PHOTO : {photo_info or 'rien à vérifier'}\n\n"
              """Réponds en JSON : {"verdict": "ok" | "corrige" | "rejete", "problemes": ["..."], "photo_ok": true/false,
"dossier": {même structure que le dossier, corrigé : cover_text, sections, caption, x_thread}}""")
    data = gem.call(VERIF_SYSTEM, prompt, temperature=0.1)
    if not isinstance(data, dict):
        raise AIError("Vérification du dossier illisible")
    return data


def render_enquete(media: dict, post: dict, photos: list, credits: list[str], out_dir: Path, size=(1080, 1350)) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    p1 = photos[0] if photos else None
    size = tuple(size)
    slides = [slide_cover(media, post, p1, credits[0] if credits else "", size)]
    for sec in post["sections"]:
        slides.append(slide_points(media, {"points_title": sec["title"], "points": sec["points"]}, size))
    slides.append(slide_cta(media, p1, size, "🔎"))
    paths = []
    for i, s in enumerate(slides, 1):
        p = out_dir / f"slide_{i}.jpg"
        s.save(p, "JPEG", quality=92)
        paths.append(p)
    x_path = out_dir / "x.jpg"
    x_image(media, photos[:2], credits[:2], emoji="🔎").save(x_path, "JPEG", quality=92)
    zip_path = out_dir / "carrousel.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as z:
        for p in paths:
            z.write(p, p.name)
    return {"slides": paths, "x": x_path, "zip": zip_path}


def run_enquete(media: dict, s: dict, blocked: list[str], set_msg) -> bool:
    from .engine import build_post   # import tardif (évite la dépendance circulaire)

    c = pick_topic(media, blocked)
    if not c:
        set_msg("Enquête : pas encore d'affaire de fond assez suivie cette semaine")
        log.info("[%s] enquête : aucune affaire assez suivie", media["name"])
        return False
    set_msg(f"Enquête : lecture des articles sur « {c['title'][:50]} »…")
    texts = _texts(c, use_browser=s.get("browser_reader", True))
    if len(texts) < 2:
        set_msg("Enquête reportée : pas assez d'articles complets accessibles")
        return False
    gem = Gemini(s.get("gemini_key", ""), s.get("ai_quality", "eco"))
    set_msg("Enquête : rédaction du dossier…")
    d = write_enquete(gem, media, c, texts)
    set_msg("Enquête : vérification des faits…")
    v = verify_enquete(gem, d, texts)
    verdict = str(v.get("verdict", "ok")).lower().replace("é", "e")
    if verdict == "rejete":
        log.warning("[%s] enquête rejetée par la vérification : %s", media["name"], v.get("problemes"))
        set_msg("Enquête rejetée par la vérification des faits")
        return False
    fixed = v.get("dossier") if isinstance(v.get("dossier"), dict) else {}
    for k in ("cover_text", "sections", "caption", "x_thread"):
        if fixed.get(k):
            d[k] = fixed[k]
    sections = []
    for sec in d["sections"][:5]:
        pts = [humanize(str(x)) for x in (sec.get("points") or []) if str(x).strip()][:5]
        if len(pts) >= 2:
            sections.append({"title": humanize(str(sec.get("title", ""))), "points": pts})
    if len(sections) < 3:
        set_msg("Enquête abandonnée : pas assez de faits vérifiés")
        return False
    thread = [humanize(str(t)) for t in (d.get("x_thread") or []) if str(t).strip()][:6]
    post = {
        "headline": "🔎 " + str(d.get("headline") or c["title"])[:100], "importance": 8,
        "sensitive": True,   # une enquête touche souvent des personnes nommées : toujours à relire
        "label": "L'ENQUÊTE", "label_emoji": "🔎",
        "cover_text": humanize(str(d.get("cover_text") or c["title"])), "points_title": sections[0]["title"],
        "points": sections[0]["points"], "sections": sections, "caption": humanize(str(d.get("caption") or "")),
        "x_text": thread[0] if thread else humanize(str(d.get("cover_text", ""))), "hashtags":
        [h if str(h).startswith("#") else f"#{h}" for h in (d.get("hashtags") or [])][:5],
        "image_subjects": [str(x) for x in (d.get("image_subjects") or [])][:2],
        "image_query_en": str(d.get("image_query_en") or ""),
    }
    verified = {"verdict": verdict if verdict in ("ok", "corrige") else "ok",
                "problemes": [str(x) for x in (v.get("problemes") or [])][:8], "photo_ok": bool(v.get("photo_ok", True))}
    ok = build_post(media, post, c, s, gem, {"thread": thread[1:], "sections": sections}, renderer=render_enquete,
                    kind_post="enquete", verified=verified, texts=texts)
    if ok:
        past = json.loads(db.kv_get(f"enq_done:{media['id']}", "[]"))
        past.append({"t": c["title"], "ts": time.time()})
        db.kv_set(f"enq_done:{media['id']}", json.dumps(past[-30:]))
        set_msg(f"🔎 Enquête prête à {datetime.now().strftime('%Hh%M')}")
    return ok
