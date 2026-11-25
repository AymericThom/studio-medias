"""Regroupe les articles qui parlent du même sujet et classe les sujets par importance.

Pur Python (TF-IDF + cosinus) : aucun coût, aucune dépendance lourde.
Plus un sujet est repris par de médias différents, plus il est important ET fiable.
"""
from __future__ import annotations

import math
import re
import time
import unicodedata
from collections import Counter

STOPWORDS = set("""
a à au aux avec ce ces cet cette ceux chez comme dans de des du elle elles en et être eu il ils je la le les leur
leurs lui ma mais me même mes moi mon ne nos notre nous on ou où par pas pour qu que qui sa se ses son sur ta te
tes toi ton tu un une vos votre vous y été étée étés est sont ont avait avaient sera seront fait faire font plus moins
très tout tous toute toutes après avant selon contre entre sans sous vers depuis lors alors aussi encore déjà
quand comment pourquoi quoi dont ainsi donc car ni or si non oui va vont peut peuvent doit doivent faut
cela ceci celui celle ça c d j l m n s t qu'il qu'elle aujourd hui hier demain an ans année années jour jours
deux trois quatre cinq six sept huit neuf dix premier première nouveau nouvelle nouveaux nouvelles
mois semaine semaines heure heures fois veut veulent annonce annoncé dit dire face
direct vidéo video photos info infos actu actualité actualités france français française
""".split())

TOKEN_RE = re.compile(r"[a-z0-9]+")


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def tokens(text: str) -> list[str]:
    text = _strip_accents(text.lower().replace("’", "'"))
    out = []
    for w in TOKEN_RE.findall(text):
        if len(w) < 3 or w in STOPWORDS:
            continue
        if len(w) > 4 and w.endswith(("s", "x")):
            w = w[:-1]
        out.append(w)
    return out


def source_key(name: str) -> str:
    """"Le Monde.fr" et "Le Monde", "Le HuffPost" et "HuffPost" = la même source."""
    s = _strip_accents(name.lower())
    s = re.sub(r"\.(fr|com|net|org|info|tv)\b", "", s)
    s = re.sub(r"^(le|la|les|l')\s*", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def vectorize(docs: list[list[str]]) -> list[dict[str, float]]:
    n = len(docs)
    df = Counter()
    for d in docs:
        df.update(set(d))
    vecs = []
    for d in docs:
        tf = Counter(d)
        v = {t: (1 + math.log(c)) * math.log((n + 1) / (df[t] + 0.5)) for t, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({t: x / norm for t, x in v.items()})
    return vecs


def cosine(a: dict, b: dict) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items())


def _add(c: dict, v: dict) -> None:
    for t, x in v.items():
        c[t] = c.get(t, 0.0) + x


def _norm(c: dict) -> dict:
    n = math.sqrt(sum(x * x for x in c.values())) or 1.0
    return {t: x / n for t, x in c.items()}


def cluster_articles(articles: list[dict], threshold: float = 0.30, extra_titles: list[str] | None = None):
    """Retourne (clusters, vecteurs des titres déjà publiés).

    Chaque cluster : {key, articles, sources, title, latest, earliest, centroid}
    """
    extra_titles = extra_titles or []
    docs = [tokens(a["title"]) * 2 + tokens(a.get("summary", "")[:240]) for a in articles]
    docs += [tokens(t) * 2 for t in extra_titles]
    vecs = vectorize(docs)
    art_vecs, extra_vecs = vecs[: len(articles)], vecs[len(articles):]

    order = sorted(range(len(articles)), key=lambda i: articles[i]["published"])
    clusters: list[dict] = []
    for i in order:
        a, v = articles[i], art_vecs[i]
        if not v:
            continue
        best, best_sim = None, 0.0
        for c in clusters:
            s = cosine(v, c["centroid"])
            if s > best_sim:
                best, best_sim = c, s
        if best is not None and best_sim >= threshold:
            best["articles"].append(a)
            _add(best["_sum"], v)
            best["centroid"] = _norm(best["_sum"])
        else:
            clusters.append({"articles": [a], "_sum": dict(v), "centroid": dict(v)})

    for c in clusters:
        arts = c["articles"]
        c["key"] = min(arts, key=lambda a: a["published"])["id"]
        names: dict[str, str] = {}
        for a in sorted(arts, key=lambda a: -a["weight"]):
            names.setdefault(source_key(a["source"]), a["source"])
        c["sources"] = list(names.values())  # sources les plus fiables d'abord
        c["latest"] = max(a["published"] for a in arts)
        c["earliest"] = min(a["published"] for a in arts)
        # titre représentatif : article le plus proche du centre, source la plus fiable
        c["title"] = max(arts, key=lambda a: (a["weight"], -abs(len(a["title"]) - 90)))["title"]
        del c["_sum"]
    return clusters, extra_vecs


def score_clusters(clusters, cfg: dict, covered: dict[str, set], posted_vecs: dict[str, list]) -> list[dict]:
    """Classe les sujets. covered / posted_vecs : par plateforme ("x", "tiktok").

    Ajoute c["done"][plateforme] = True si le sujet a déjà été traité sur cette plateforme.
    Les sujets traités partout sont retirés.
    """
    ed = cfg["editorial"]
    boosts = [k.lower() for k in ed.get("boost_keywords", [])]
    blocked = [k.lower() for k in ed.get("blocked_keywords", [])]
    now = time.time()
    ranked = []
    for c in clusters:
        text = " ".join(a["title"] + " " + a.get("summary", "")[:200] for a in c["articles"]).lower()
        titles = " ".join(a["title"] for a in c["articles"]).lower()
        if any(b in titles for b in blocked):
            continue
        c["done"] = {}
        for platform in covered:
            ids = covered.get(platform, set())
            pvs = posted_vecs.get(platform, [])
            c["done"][platform] = any(a["id"] in ids for a in c["articles"]) or (
                bool(pvs) and max(cosine(c["centroid"], pv) for pv in pvs) >= 0.45
            )
        if c["done"] and all(c["done"].values()):
            continue
        n_src = len(c["sources"])
        best_w = max(a["weight"] for a in c["articles"])
        hits = sum(1 for k in boosts if k in text)
        age_h = (now - c["latest"]) / 3600
        recency = 2.0 if age_h < 1 else 1.0 if age_h < 3 else 0.0
        c["n_sources"] = n_src
        c["trusted"] = any(a["trusted"] for a in c["articles"])
        c["score"] = round(2.2 * n_src + min(3.0, 1.2 * hits) + recency + (best_w - 1) * 3, 2)
        ranked.append(c)
    ranked.sort(key=lambda c: c["score"], reverse=True)
    return ranked
