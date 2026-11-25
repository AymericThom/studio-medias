"""Moteur 100 % automatique.

Toutes les ~10 min, pour chaque média, le studio relit ses sources (gratuit, sans IA) et regroupe les sujets.
Il n'appelle l'IA que s'il y a un sujet CHAUD (repris par plusieurs médias, tout récent) ou si le compte n'a rien
publié depuis trop longtemps. Un sujet déjà soumis à l'IA n'est pas re-soumis, sauf s'il prend de l'ampleur.
"""
from __future__ import annotations

import json
import logging
import queue
import re
import shutil
import threading
import time
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

from . import db
from .ai import AIError, Gemini, verify_post, write_posts
from .cluster import cluster_articles, score_clusters
from .config import BRAND, POSTS, TIMEZONE, get_media, load_medias, load_settings
from .fulltext import fetch_cluster_texts
from .notify import send as notify
from .images import find_images, wiki_paused
from .sources import fetch_all
from .visuals import avatar, make_tiktok, render_post

log = logging.getLogger("studio")
TZ = ZoneInfo(TIMEZONE)
BOOST = ["urgent", "alerte", "officiel", "annonce", "démission", "record", "explosion", "accord", "condamné",
         "historique", "choc", "inédit", "guerre", "élection", "présidentielle", "mort de", "décès", "victoire",
         "sacre", "finale", "transfert", "rachat", "faillite", "hausse", "baisse", "grève"]
URL_RE = re.compile(r"https?://\S+|www\.\S+|\b[\w-]+\.(?:fr|com|net|org|io|info|eu|tv|co)\b(?:/\S*)?", re.I)
FRESH_H = 12          # un sujet doit avoir un article daté de moins de 12 h
HOT_RECENT_H = 3      # et, pour être "chaud", un article de moins de 3 h


def weighted_len(text: str) -> int:
    return sum(1 if ord(ch) <= 0x10FF or 0x2000 <= ord(ch) <= 0x201F else 2 for ch in text)


def clean_tweet(text: str) -> str:
    text = URL_RE.sub("", text or "").replace("**", "")
    text = re.sub(r"(?<!\w)@(\w+)", r"\1", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    if weighted_len(text) <= 280:
        return text
    while weighted_len(text) > 279 and " " in text:
        text = text[: text.rfind(" ")]
    return text.rstrip(" ,;:") + "…"


def slug(text: str, n: int = 36) -> str:
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:n] or "post"


def ensure_avatar(media: dict) -> None:
    BRAND.mkdir(parents=True, exist_ok=True)
    p = BRAND / f"{media['id']}.png"
    sig = f"v2|{media['name']}|{media['color']}"
    sig_file = BRAND / f"{media['id']}.sig"
    if not p.exists() or not sig_file.exists() or sig_file.read_text(encoding="utf-8") != sig:
        avatar(media).save(p)
        sig_file.write_text(sig, encoding="utf-8")


def rel(path) -> str:
    return path.relative_to(POSTS).as_posix()


def files_rel(files: dict) -> dict:
    out = {"slides": [rel(x) for x in files["slides"]], "x_image": rel(files["x"]), "zip": rel(files["zip"])}
    if files.get("tiktok"):
        out.update(tiktok_slides=[rel(x) for x in files["tiktok"]], tiktok_zip=rel(files["tiktok_zip"]))
    return out


def save_photo(photos: list, out_dir) -> str:
    """Photo principale sans texte, gardée pour « L'essentiel du jour »."""
    if not photos:
        return ""
    try:
        p = out_dir / "photo.jpg"
        photos[0].convert("RGB").save(p, "JPEG", quality=90)
        return rel(p)
    except Exception:
        return ""


def with_tiktok(files: dict, out_dir) -> dict:
    """Ajoute la version TikTok (9:16 plein écran) des images du carrousel."""
    try:
        return {**files, **make_tiktok(files["slides"], out_dir)}
    except Exception as ex:
        log.warning("Version TikTok impossible : %s", ex)
        return files


def full_caption(base: str, credits: list[str], hashtags: list[str], question: str = "", sources=None) -> str:
    """Description Instagram : texte, question pour les commentaires, sources citées (crédibilité), photo, hashtags."""
    caption = base
    if question:
        caption += "\n\n" + question
    if sources:
        caption += "\n\nSources : " + ", ".join(sources[:4])
    if credits:
        caption += "\nPhoto : " + " · ".join(credits)
    if hashtags:
        caption += "\n\n" + " ".join(hashtags)
    return caption


def tiktok_caption(base: str, hashtags: list[str], question: str = "") -> str:
    """TikTok : court (on lit les images, pas la légende), mots-clés pour la recherche TikTok, hashtags."""
    paras = [x.strip() for x in (base or "").split("\n\n") if x.strip()]
    text = "\n\n".join(paras[:2])
    if question:
        text += "\n\n" + question
    tags = list(dict.fromkeys(list(hashtags)[:4] + ["#actu", "#info"]))
    return f"{text}\n\n{' '.join(tags)}".strip()


def proper_subjects(subjects: list[str], c: dict) -> list[str]:
    """Garde seulement les vrais noms propres cités dans les articles (évite « Radar » -> photo d'un radar militaire)."""
    text = " ".join(a["title"] + " " + a.get("summary", "") for a in c["articles"])
    out = []
    for s in subjects:
        words = s.split()
        if len(words) >= 2:
            if s in text or (words[-1][:1].isupper() and re.search(r"" + re.escape(words[-1]) + r"", text)):
                out.append(s)
        elif s[:1].isupper() and re.search(r"[a-zà-ÿ,]\s+" + re.escape(s) + r"", text):
            out.append(s)          # mot seul : doit apparaître avec une majuscule au milieu d'une phrase
    return out


def _mini_articles(c: dict) -> list[dict]:
    return [{"source": a["source"], "weight": a["weight"], "link": a["link"], "image": a.get("image", "")}
            for a in sorted(c["articles"], key=lambda a: -a["weight"])[:6]]


def rerender(pid: int, keep_better: bool = False) -> bool:
    """Refait photos et visuels d'un post (ex. si Wikipédia était momentanément indisponible)."""
    post = db.get_post(pid)
    if not post or "cover_text" not in post["data"]:
        return False
    s = load_settings()
    media = get_media(post["media"], s)
    d = post["data"]
    found, kind = find_images(d.get("image_subjects", []), d.get("image_query_en", ""), s.get("pexels_key", ""),
                              d.get("articles", []), s.get("press_photo", True))
    if keep_better and kind != "wiki":
        return False      # réparation auto : on ne remplace que par une vraie photo Wikipédia
    photos, credits = [f[0] for f in found], [f[1] for f in found]
    if d.get("kind") == "enquete":
        from .enquete import render_enquete
        files = render_enquete(media, d, photos, credits, POSTS / d["dir"], s.get("carousel_size", [1080, 1350]))
    else:
        files = render_post(media, d, photos, credits, POSTS / d["dir"], s.get("carousel_size", [1080, 1350]))
    files = with_tiktok(files, POSTS / d["dir"])
    d["photo"] = save_photo(photos, POSTS / d["dir"])
    d.update(files_rel(files), credits=credits, rev=d.get("rev", 1) + 1, photo_kind=kind, press=kind == "press",
             caption=full_caption(d.get("caption_base", d["caption"]), credits, d.get("hashtags", []),
                                  d.get("question", ""), d.get("sources")))
    db.update_data(pid, d)
    log.info("[%s] visuels refaits : %s (%d photo(s))", media["name"], post["headline"], len(photos))
    return True


def build_post(media: dict, p: dict, c: dict, s: dict, gem: Gemini, extra: dict | None = None,
               renderer=render_post, kind_post: str = "actu", verified: dict | None = None,
               texts: list[dict] | None = None) -> bool:
    """Vérifie les faits sur les articles complets, trouve la photo (et vérifie la personne), crée les visuels, enregistre.
    Retourne False si le vérificateur rejette le sujet (fait principal non confirmé)."""
    media_id, name = media["id"], media["name"]
    arts = _mini_articles(c)
    p["image_subjects"] = proper_subjects(p.get("image_subjects", []), c)
    found, kind = find_images(p["image_subjects"], p.get("image_query_en", ""), s.get("pexels_key", ""), arts,
                              s.get("press_photo", True))
    photo_info = ""
    if kind == "wiki":
        metas = [f[2] for f in found if len(f) > 2]
        photo_info = " ; ".join(f"page Wikipédia « {m.get('title')} » ({m.get('description') or 'sans description'})"
                                for m in metas)
    if texts is None:
        texts = fetch_cluster_texts(c["articles"], use_browser=s.get("browser_reader", True))
    try:
        v = verified if verified is not None else verify_post(gem, p, texts, photo_info)
    except AIError as ex:
        log.warning("[%s] vérification impossible (%s) : post gardé, marqué non vérifié", name, ex)
        v = {"verdict": "non_verifie", "problemes": ["Vérificateur indisponible (Gemini saturé)"], "photo_ok": True}
    if v["verdict"] == "non_verifie" and p.get("sensitive"):
        v = {**v, "verdict": "rejete", "problemes": v["problemes"] + ["Sujet sensible impossible à vérifier sur les articles complets : écarté par prudence"]}
    if v["verdict"] == "rejete":
        log.warning("[%s] REJETÉ par la vérification : %s | %s", name, p["headline"], " / ".join(v["problemes"]))
        if not any("indisponible" in x for x in v["problemes"]):   # Gemini saturé : le sujet pourra être retenté
            db.mark_covered(media_id, [a["id"] for a in c["articles"]])
        return False
    for k in ("x_text", "cover_text", "points_title", "points", "caption"):
        if k in v:
            p[k] = v[k]
    if kind == "wiki" and not v.get("photo_ok", True):
        log.warning("[%s] photo Wikipédia jugée incorrecte (%s) : on cherche une autre photo", name, photo_info)
        v["problemes"].append(f"Photo écartée : {photo_info}")
        found, kind = find_images([], p.get("image_query_en", ""), s.get("pexels_key", ""), arts,
                                  s.get("press_photo", True), skip_wiki=True)
    photos, credits = [f[0] for f in found], [f[1] for f in found]
    t = datetime.now(TZ)
    out = POSTS / media_id / t.strftime("%Y-%m-%d") / f"{t.strftime('%H%M%S')}_{slug(p['headline'])}"
    files = with_tiktok(renderer(media, p, photos, credits, out, s.get("carousel_size", [1080, 1350])), out)
    photo_rel = save_photo(photos, out)
    question = "" if p.get("sensitive") else p.get("question", "")
    data = {
        "kind": kind_post, "x_text": clean_tweet(p["x_text"]),
        "caption": full_caption(p["caption"], credits, p.get("hashtags", []), question, c["sources"]),
        "tiktok_text": tiktok_caption(p["caption"], p.get("hashtags", []), question),
        "question": question, "rubrique": p.get("rubrique", ""),
        "caption_base": p["caption"], "hashtags": p.get("hashtags", []), "label": p.get("label", ""),
        "label_emoji": p.get("label_emoji", ""), "cover_text": p["cover_text"], "points_title": p.get("points_title", ""),
        "points": p.get("points", []), "image_subjects": p["image_subjects"], "image_query_en": p.get("image_query_en", ""),
        "sources": c["sources"], "credits": credits, "press": kind == "press", "photo_kind": kind, "repairs": 0,
        "articles": arts, "news_time": c.get("latest_dated", c["latest"]),
        "verif": {"verdict": v["verdict"], "problemes": v["problemes"], "textes": [x["source"] for x in texts]},
        "dir": rel(out), "rev": 1, "photo": photo_rel, **files_rel(files), **(extra or {}),
    }
    db.add_post(media_id, p["headline"], p["importance"], p["sensitive"], c["n_sources"], data)
    db.mark_covered(media_id, [a["id"] for a in c["articles"]])
    log.info("[%s] post prêt (%s) : %s", name, v["verdict"], p["headline"])
    return True


class Engine:
    def __init__(self):
        db.init()
        self.q: queue.Queue = queue.Queue()
        self.state: dict[str, dict] = {}
        self.lock = threading.Lock()
        for m in load_medias()[0]:
            ensure_avatar(m)
            self.state[m["id"]] = {"status": "idle", "msg": "En attente du premier passage…",
                                   "last": float(db.kv_get(f"last_check:{m['id']}", 0))}
        threading.Thread(target=self._worker, daemon=True).start()
        threading.Thread(target=self._scheduler, daemon=True).start()

    # ------------------------------------------------------------------ file d'attente
    def request(self, media_id: str, manual: bool = True, task: str = "actu") -> bool:
        with self.lock:
            st = self.state.setdefault(media_id, {"status": "idle", "msg": "", "last": 0})
            if st["status"] in ("queued", "running"):
                return False
            st.update(status="queued", msg="En file d'attente…")
        self.q.put((media_id, manual, task))
        return True

    def _set(self, media_id: str, **kw) -> None:
        with self.lock:
            self.state.setdefault(media_id, {}).update(kw)

    def _worker(self) -> None:
        while True:
            media_id, manual, task = self.q.get()
            ok = False
            try:
                if task == "enquete":
                    ok = self.run_enquete(media_id)
                else:
                    self.run_media(media_id, manual)
            except Exception as ex:
                log.exception("Erreur inattendue (%s)", media_id)
                self._set(media_id, msg=f"Erreur : {ex}")
            finally:
                now = time.time()
                if task == "enquete":   # réussie : prochaine dans X jours ; sinon on réessaie demain
                    days = load_settings().get("enquete_every_days", 3)
                    db.kv_set(f"last_enquete:{media_id}", now if ok else now - max(0, days - 1) * 86400)
                else:
                    db.kv_set(f"last_check:{media_id}", now)
                self._set(media_id, status="idle", last=now)

    def run_enquete(self, media_id: str) -> bool:
        from .enquete import run_enquete

        s = load_settings()
        media = get_media(media_id, s)
        _, common_blocked = load_medias(s)
        self._set(media_id, status="running", msg="Enquête : recherche de l'affaire de la semaine…")
        try:
            ok = run_enquete(media, s, common_blocked + media.get("extra_blocked", []),
                             lambda m: self._set(media_id, msg=m))
            if ok:
                notify(f"🔎 {media['name']} · nouvelle enquête prête", "Le dossier de fond est prêt à relire dans le studio.",
                       ["mag"], kind="ready")
            return ok
        except AIError as ex:
            self._set(media_id, msg=f"Enquête : {ex}")
            return False

    def _scheduler(self) -> None:
        time.sleep(8)
        while True:
            try:
                s = load_settings()
                if s.get("auto", True) and s.get("gemini_key"):
                    hour = datetime.now(TZ).hour
                    for idx, m in enumerate(load_medias(s)[0]):
                        if not m.get("enabled", True):
                            continue
                        last_enq = float(db.kv_get(f"last_enquete:{m['id']}", 0))
                        start_h = s.get("enquete_hour", 9) + idx      # enquêtes étalées : 1 média par heure
                        if (s.get("enquete_every_days", 3) > 0 and start_h <= hour < 23
                                and time.time() - last_enq >= s.get("enquete_every_days", 3) * 86400 - 3600):
                            self.request(m["id"], manual=False, task="enquete")
                            continue
                        last = float(db.kv_get(f"last_check:{m['id']}", 0))
                        if time.time() - last >= s.get("check_every_min", 10) * 60:
                            self.request(m["id"], manual=False)
                    from .recap import run_recaps
                    run_recaps(load_medias(s)[0], s)
                self._repair_photos()
                from .publish import autopublish_tick
                autopublish_tick()
            except Exception:
                log.exception("Planificateur")
            time.sleep(30)

    def _repair_photos(self) -> None:
        """Retente la vraie photo (Wikipédia) des posts récents pas encore publiés, quand Wikipédia répond à nouveau."""
        busy = not self.q.empty() or any(st.get("status") == "running" for st in self.state.values())
        if wiki_paused() or busy or time.time() - getattr(self, "_last_repair", 0) < 300:
            return
        self._last_repair = time.time()
        for p in db.posts(None, time.time() - 6 * 3600):
            d = p["data"]
            if (d.get("photo_kind", "wiki") != "wiki" and d.get("image_subjects") and d.get("repairs", 0) < 3
                    and not p["posted_x"] and not p["posted_social"]):
                d["repairs"] = d.get("repairs", 0) + 1
                db.update_data(p["id"], d)
                if rerender(p["id"], keep_better=True):
                    log.info("Photo réparée : %s", p["headline"])
                return   # un seul par tour pour ménager Wikipédia

    # ------------------------------------------------------------------ sujets déjà soumis à l'IA
    @staticmethod
    def _evaluated(media_id: str) -> dict:
        try:
            ev = json.loads(db.kv_get(f"eval:{media_id}", "{}"))
        except json.JSONDecodeError:
            ev = {}
        cutoff = time.time() - 2 * 86400
        return {k: v for k, v in ev.items() if v[1] >= cutoff}

    @staticmethod
    def _save_evaluated(media_id: str, ev: dict, clusters: list[dict]) -> None:
        for c in clusters:
            ev[c["key"]] = [c["n_sources"], time.time()]
        db.kv_set(f"eval:{media_id}", json.dumps(ev))

    # ------------------------------------------------------------------ génération
    def run_media(self, media_id: str, manual: bool) -> int:
        s = load_settings()
        media = get_media(media_id, s)
        if not media:
            return 0
        _, common_blocked = load_medias(s)
        ensure_avatar(media)
        name = media["name"]
        now = time.time()
        local = datetime.now(TZ)
        midnight = local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        self._set(media_id, status="running", msg="Lecture des sources…")

        # 1) lecture des sources + regroupement (gratuit)
        db.add_articles(media_id, fetch_all(media["feeds"]))
        recent = db.recent_articles(media_id, FRESH_H)
        done = [p["headline"] for p in db.posts(media_id, now - 48 * 3600)]
        others_titles = [p["headline"] for p in db.posts(None, now - 36 * 3600) if p["media"] != media_id]
        # un sujet déjà publié par N'IMPORTE LEQUEL des 5 médias est écarté (pas de doublon entre comptes)
        clusters, extra = cluster_articles(recent, 0.30, done + others_titles)
        cfg = {"editorial": {"boost_keywords": BOOST,
                             "blocked_keywords": common_blocked + media.get("extra_blocked", [])}}
        ranked = score_clusters(clusters, cfg, {"item": db.covered_ids(media_id)}, {"item": extra})
        fresh = []
        for c in ranked:   # actu du jour uniquement : au moins un article réellement daté de moins de 12 h
            dated = [a["published"] for a in c["articles"] if a.get("dated")]
            if dated and max(dated) >= now - FRESH_H * 3600:
                c["latest_dated"] = max(dated)
                fresh.append(c)
        ev = self._evaluated(media_id)
        new = [c for c in fresh if c["key"] not in ev or c["n_sources"] >= ev[c["key"]][0] + 2]
        min_src = media.get("min_sources", 2)
        solid = [c for c in new if c["n_sources"] >= min_src]
        if len(solid) < 3:
            solid += [c for c in new if c not in solid and c.get("trusted")][: 3 - len(solid)]

        # 2) faut-il appeler l'IA ?
        hot_n = media.get("hot_sources", s.get("hot_sources", 3))
        boosts = [b.lower() for b in BOOST]

        def is_hot(c):
            recent_enough = c["latest_dated"] >= now - HOT_RECENT_H * 3600
            titles = " ".join(a["title"] for a in c["articles"]).lower()
            return recent_enough and (c["n_sources"] >= hot_n or (c["n_sources"] >= 2 and any(b in titles for b in boosts)))

        h0, h1 = s.get("hours", [7, 23])
        active = h0 <= local.hour < h1
        hot = [c for c in solid if is_hot(c)] if active else [c for c in solid if c["n_sources"] >= max(5, hot_n + 2)]
        last_post = max([p["created"] for p in db.posts(media_id, now - 2 * 86400)], default=0)
        silent = active and now - last_post >= s.get("max_silence_h", 3) * 3600
        last_gen = float(db.kv_get(f"last_gen:{media_id}", 0))
        budget = min(s.get("per_run", 2), s.get("max_per_day", 10) - db.count_today(media_id, midnight))
        stamp = local.strftime("%Hh%M")
        if manual:
            budget = max(budget, 1)
            cands = solid
        else:
            if budget <= 0:
                self._set(media_id, msg=f"Quota du jour atteint · vérifié à {stamp}")
                return 0
            super_hot = [c for c in hot if c["n_sources"] >= hot_n + 2 and c["latest_dated"] >= now - 3600]
            if now - last_gen < s.get("min_gap_min", 20) * 60 and not super_hot:
                wait = int((s.get("min_gap_min", 20) * 60 - (now - last_gen)) / 60) + 1
                self._set(media_id, msg=f"{len(hot)} sujet(s) chaud(s) · prochaine génération possible dans {wait} min")
                return 0
            if hot:
                cands = hot + [c for c in solid if c not in hot]
            elif silent and solid:
                cands = solid
            else:
                self._set(media_id, msg=f"Rien de chaud pour l'instant · vérifié à {stamp}")
                return 0
        cands = cands[:8]
        if not cands:
            self._set(media_id, msg=f"Pas de nouveau sujet solide · vérifié à {stamp}")
            return 0

        # 3) rédaction (1 appel IA)
        reason = "manuel" if manual else ("sujet chaud" if hot else "relance (rien publié depuis un moment)")
        log.info("[%s] génération (%s) sur %d sujet(s)", name, reason, len(cands))
        self._set(media_id, msg="Rédaction par l'IA…")
        try:
            all_medias = load_medias(s)[0]
            others = [f"[{m['name']}] {p['headline']}" for m in all_medias if m["id"] != media_id
                      for p in db.posts(m["id"], now - 24 * 3600)]
            niches = [f"{m['name']} = {m['niche'].split(':')[0]}" for m in all_medias if m["id"] != media_id]
            rub: dict[str, int] = {r: 0 for r in media.get("rubriques", [])}
            for p in db.posts(media_id, midnight):
                r = p["data"].get("rubrique")
                if r:
                    rub[r] = rub.get(r, 0) + 1
            posts = write_posts(Gemini(s.get("gemini_key", ""), s.get("ai_quality", "eco")), media, cands, done, budget,
                                others, niches, rub)
        except AIError as ex:
            self._set(media_id, msg=str(ex))
            log.error("[%s] %s", name, ex)
            return 0
        db.kv_set(f"last_gen:{media_id}", time.time())
        self._save_evaluated(media_id, ev, cands)
        if not posts:
            self._set(media_id, msg=f"L'IA n'a rien retenu d'assez fort · vérifié à {stamp}")
            log.info("[%s] aucun sujet retenu par l'IA", name)
            return 0

        # 4) vérification des faits sur les articles complets + photos + visuels
        made = 0
        gem = Gemini(s.get("gemini_key", ""), s.get("ai_quality", "eco"))
        for p in posts:
            c = p["cluster"]
            self._set(media_id, msg=f"Vérification : {p['headline'][:50]}…")
            if build_post(media, p, c, s, gem, {"hot": c in hot}):
                made += 1
        for old in db.prune(s.get("keep_days", 7)):
            d = POSTS / old["data"].get("dir", "__none__")
            if d.exists() and POSTS.resolve() in d.resolve().parents:
                shutil.rmtree(d, ignore_errors=True)
        self._set(media_id, msg=f"{made} nouveau(x) post(s) à {datetime.now(TZ).strftime('%Hh%M')}")
        if made:
            from .publish import _route
            cfg_pub = (s.get("publish") or {}).get(media_id, {})
            auto = cfg_pub.get("enabled") and any(_route(x, cfg_pub, s) for x in ("x", "instagram"))
            heads = [p["headline"] for p in db.posts(media_id, now - 60)][:made]
            notify(f"🆕 {name} · {made} post(s) prêt(s)" + (" · Insta/X en auto, TikTok à poster" if auto else ""),
                   "\n".join(f"• {h}" for h in heads), ["newspaper"], kind="ready")
        return made
