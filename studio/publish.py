"""Publication automatique : Instagram en direct (API Meta, gratuite), X et TikTok via Buffer (gratuit).

Buffer (API officielle GraphQL, https://developers.buffer.com) : l'offre gratuite permet 3 réseaux par compte Buffer.
Le studio accepte jusqu'à 6 comptes Buffer : idéalement 1 par média (X + Instagram + TikTok), + 1 pour le compte X généraliste « Gros Titre ».
Une chaîne Buffer est notée « n:identifiant » (n = numéro du compte Buffer ; sans préfixe = compte n°1).
Les images doivent avoir une adresse publique : le studio les sert lui-même (studio hébergé ou tunnel Cloudflare
gratuit), via des liens signés. Aucune image n'est envoyée chez un hébergeur tiers.

Garde-fous : seuls les posts dont les faits sont vérifiés (✅ ou ✏️), non sensibles, sont publiés automatiquement.
Les autres restent à valider dans le studio (et une notification te prévient).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

from . import db
from .config import POSTS, TIMEZONE, load_medias, load_settings, save_settings
from .notify import send
from .publishers import instagram_publish, instagram_refresh, x_publish

log = logging.getLogger("studio.publish")
API = "https://api.buffer.com"
PLATFORMS = {"x": "X", "instagram": "Instagram", "tiktok": "TikTok"}
BUFFER_SLOTS = ("buffer_key", "buffer_key2", "buffer_key3", "buffer_key4", "buffer_key5", "buffer_key6")


def buffer_ref(ref: str, s: dict) -> tuple[str, str]:
    """« 2:abc » -> (clé du compte Buffer n°2, « abc »)."""
    n, cid = 1, (ref or "").strip()
    head, sep, tail = cid.partition(":")
    if sep and head.isdigit():
        n, cid = int(head), tail
    key = s.get(BUFFER_SLOTS[n - 1], "") if 1 <= n <= len(BUFFER_SLOTS) else ""
    return key, cid


class BufferError(RuntimeError):
    pass


class Buffer:
    def __init__(self, key: str):
        self.key = (key or "").strip()

    def q(self, query: str, variables: dict | None = None) -> dict:
        if not self.key:
            raise BufferError("Aucune clé Buffer : ajoute-la dans Réglages")
        r = requests.post(API, json={"query": query, "variables": variables or {}}, timeout=30,
                          headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
        if r.status_code == 401:
            raise BufferError("Clé Buffer refusée")
        if r.status_code == 429:
            raise BufferError("Limite de l'API Buffer atteinte, nouvel essai plus tard")
        try:
            data = r.json()
        except Exception:
            raise BufferError(f"Réponse Buffer illisible (HTTP {r.status_code})")
        if data.get("errors"):
            raise BufferError("Buffer : " + "; ".join(str(e.get("message")) for e in data["errors"])[:300])
        return data.get("data") or {}

    def channels(self) -> list[dict]:
        orgs = self.q("query { account { organizations { id name } } }")["account"]["organizations"]
        out = []
        for org in orgs:
            chans = self.q("""query GetChannels($input: ChannelsInput!) {
                channels(input: $input) { id name displayName service avatar isDisconnected } }""",
                           {"input": {"organizationId": org["id"]}})["channels"]
            out += [{**c, "org": org.get("name", "")} for c in chans]
        return out

    def create_post(self, channel_id: str, text: str, image_urls: list[str], delay_s: int = 90) -> str:
        due = (datetime.now(timezone.utc) + timedelta(seconds=delay_s)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        data = self.q("""mutation CreatePost($input: CreatePostInput!) {
            createPost(input: $input) {
              ... on PostActionSuccess { post { id } }
              ... on MutationError { message } } }""",
                      {"input": {"text": text, "channelId": channel_id, "schedulingType": "automatic",
                                 "mode": "customScheduled", "dueAt": due,
                                 "assets": [{"image": {"url": u}} for u in image_urls]}})
        res = data.get("createPost") or {}
        if res.get("message"):
            raise BufferError(f"Buffer a refusé le post : {res['message']}")
        post = res.get("post") or {}
        if not post.get("id"):
            raise BufferError("Buffer n'a pas renvoyé de post")
        return post["id"]


# ------------------------------------------------------------------ adresses publiques des images
def _secret() -> str:
    s = load_settings()
    if not s.get("pub_secret"):
        save_settings({"pub_secret": secrets.token_hex(16)})
        s = load_settings()
    return s["pub_secret"]


def pub_token(rel: str) -> str:
    return hmac.new(_secret().encode(), rel.encode(), hashlib.sha256).hexdigest()[:20]


def public_image_url(rel: str) -> str:
    """Adresse publique signée d'une image, servie par le studio lui-même (adresse hébergée ou tunnel Cloudflare).
    Aucune image n'est envoyée chez un hébergeur tiers."""
    from .tunnel import current_url

    st = load_settings()
    if st.get("public_static_url"):                       # mode GitHub Pages : images publiques telles quelles
        return f"{st['public_static_url'].rstrip('/')}/files/{rel}"
    base = (st.get("public_url") or current_url() or "").rstrip("/")
    if not base:
        raise BufferError("Pas d'adresse publique : active le tunnel Cloudflare dans Réglages (ou renseigne l'adresse "
                          "du studio hébergé) pour que Buffer puisse récupérer les images")
    return f"{base}/pub/{pub_token(rel)}/{rel}"


# ------------------------------------------------------------------ publication automatique
TZ = ZoneInfo(TIMEZONE)
# Chaque réseau a son rythme. X : la vitesse et le volume (tout ce qui est vérifié, vite).
# Instagram et TikTok : seulement le meilleur, bien espacé (trop de posts fait baisser la portée de chacun).
RHYTHM = {
    "x": {"max": 20, "gap": 15, "age_h": 3, "hours": (6, 24), "min_imp": 0},
    "instagram": {"max": 5, "gap": 120, "age_h": 8, "hours": (8, 23), "min_imp": 6},
    "tiktok": {"max": 4, "gap": 150, "age_h": 10, "hours": (9, 23), "min_imp": 6},
    "hub": {"max": 30, "gap": 12, "age_h": 2, "hours": (6, 24), "min_imp": 8},
}


def rhythm(platform: str, s: dict) -> dict:
    """Rythme par défaut, modifiable dans Réglages (max par jour, écart en minutes)."""
    r = dict(RHYTHM[platform])
    r.update({k: int(v) for k, v in ((s.get("publish_rhythm") or {}).get(platform) or {}).items()
              if k in ("max", "gap") and str(v).isdigit()})
    return r


# Ce qui ne part JAMAIS tout seul, même vérifié : les drames humains.
HARD = ["attentat", "terroris", "viol", "meurtre", "assassinat", "suicide", "otage", "fusillade", "pédo", "mineur",
        "infanticide", "féminicide", "agression sexuelle", "mort", "tué", "décès", "décéd", "blessé", "victime", "enfant",
        "drame", "noyade", "massacre", "bombardement"]


def _ok_sensitive(p: dict, s: dict) -> bool:
    """Sujet sensible publiable automatiquement ? Oui si tu l'as autorisé pour tout, ou s'il est politico-judiciaire
    (perquisition, enquête, procès…), vérifié sans aucune correction et repris par au moins 2 médias."""
    if s.get("auto_sensitive", False):
        return True
    d = p["data"]
    text = f"{p['headline']} {d.get('cover_text', '')} {d.get('x_text', '')}".lower()
    return (s.get("auto_judiciaire", True) and (d.get("verif") or {}).get("verdict") == "ok"
            and p.get("n_sources", 0) >= 2 and not any(w in text for w in HARD))


def gen(p: dict) -> int:
    """Intérêt pour le grand public (posts récents) ; à défaut, l'importance dans la niche."""
    return int(p["data"].get("interet_general") or p["importance"])


def _eligible(p: dict, s: dict, platform: str = "x") -> bool:
    d, r = p["data"], rhythm(platform, s)
    v = d.get("verif") or {}
    if p["hidden"] or v.get("verdict") not in ("ok", "corrige"):
        return False
    if time.time() - p["created"] > r["age_h"] * 3600 * (2 if d.get("kind") in ("enquete", "recap") else 1):
        return False
    score = gen(p) if platform == "hub" else p["importance"]
    if score < r["min_imp"] and not (d.get("hot") and platform != "hub"):
        return False
    if d.get("kind") == "enquete" and not s.get("auto_enquetes", False):
        return False
    if platform == "hub" and d.get("kind") == "recap":     # le récap d'un média n'a rien à faire sur le compte généraliste
        return False
    if platform == "hub" and p.get("n_sources", 0) < 3:    # une vraie grosse info est reprise par au moins 3 médias
        return False
    if p["sensitive"] and not _ok_sensitive(p, s):
        return False
    return True


def _route(platform: str, cfg: dict, s: dict) -> str | None:
    """Comment publier sur ce réseau pour ce média : « direct » (API officielle), « buffer », ou rien."""
    if platform == "instagram" and cfg.get("ig_user_id") and cfg.get("ig_token"):
        return "direct"
    if cfg.get(platform) and buffer_ref(cfg[platform], s)[0]:     # Buffer gratuit, avant l'API X payante
        return "buffer"
    if platform == "x" and cfg.get("x_token") and cfg.get("x_secret") and s.get("x_api_key") and s.get("x_api_secret"):
        return "direct"
    return None


def publish_post(p: dict, platform: str, cfg: dict, s: dict, route: str) -> str:
    d = p["data"]
    if platform == "x":
        text, images = d["x_text"], [d["x_image"]]
    elif platform == "tiktok":
        text, images = d.get("tiktok_text") or d["caption"], list(d.get("tiktok_slides") or d["slides"])
    else:
        text, images = d["caption"], list(d["slides"])
    if route == "direct" and platform == "x":
        return x_publish(s["x_api_key"], s["x_api_secret"], cfg["x_token"], cfg["x_secret"], text, POSTS / images[0])
    urls = [public_image_url(rel) for rel in images]
    if route == "direct" and platform == "instagram":
        return instagram_publish(cfg["ig_user_id"], cfg["ig_token"], urls, text)
    key, channel = buffer_ref(cfg[platform], s)
    return Buffer(key).create_post(channel, text, urls)


def _refresh_instagram_tokens(s: dict) -> None:
    """Les jetons Instagram durent 60 jours : on les prolonge automatiquement tous les 20 jours."""
    cfg_all = s.get("publish") or {}
    changed = False
    for mid, cfg in cfg_all.items():
        if cfg.get("ig_token") and time.time() - float(cfg.get("ig_refreshed", 0)) > 20 * 86400:
            try:
                cfg["ig_token"] = instagram_refresh(cfg["ig_token"])
                cfg["ig_refreshed"] = time.time()
                changed = True
            except Exception as ex:
                log.warning("Jeton Instagram (%s) non prolongé : %s", mid, ex)
                cfg["ig_refreshed"] = time.time() - 19 * 86400     # nouvel essai dans 24 h
                changed = True
    if changed:
        save_settings({"publish": cfg_all})


def _try(acct: str, label: str, name: str, cand: dict, platform: str, cfg: dict, s: dict, route: str,
         tag: str, day: str, count: int) -> bool:
    done_key = f"pub_done:{cand['id']}:{tag}"
    db.kv_set(done_key, "en cours")
    try:
        remote = publish_post(cand, platform, cfg, s, route)
    except Exception as ex:
        db.kv_set(done_key, "")
        fail = f"pub_fail:{cand['id']}:{tag}"
        db.kv_set(fail, int(db.kv_get(fail, 0)) + 1)
        db.kv_set(f"pub_last:{acct}", time.time())       # évite de réessayer en boucle
        log.error("[%s] publication %s impossible : %s", name, label, ex)
        send(f"⚠️ {name} · échec sur {label}", f"{cand['headline']}\n{ex}", ["warning"], 4, kind="error")
        return False
    db.kv_set(done_key, remote)
    db.kv_set(f"pub_last:{acct}", time.time())
    db.kv_set(f"pub_count:{acct}:{day}", count + 1)
    log.info("[%s] publié sur %s (%s) : %s", name, label, route, cand["headline"])
    return True


def _join(labels: list[str]) -> str:
    return labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " et " + labels[-1]


def _notify_published(done: dict) -> None:
    """UNE notification par article, avec tous les réseaux où il vient de partir.
    Si l'article part ailleurs plus tard (Instagram 2 h après X, par exemple), petite notification silencieuse."""
    for pid, info in done.items():
        key = f"notif_pub:{pid}"
        first = not db.kv_get(key)
        db.kv_set(key, "1")
        where = _join(info["labels"])
        if first:
            send(f"✅ {info['name']} · publié sur {where}", info["headline"], ["white_check_mark"], kind="published")
        else:
            send(f"↪️ {info['name']} · aussi sur {where}", info["headline"], ["arrow_right_hook"], 2, kind="published")


def _ready(acct: str, platform: str, s: dict, day: str, hour: int, urgent: bool = False) -> int | None:
    """Nombre de posts déjà faits aujourd'hui si le compte peut publier maintenant, sinon None."""
    r = rhythm(platform, s)
    if not (r["hours"][0] <= hour < r["hours"][1]):
        return None
    count = int(db.kv_get(f"pub_count:{acct}:{day}", 0))
    gap = min(r["gap"], 5) if urgent else r["gap"]
    if count >= r["max"] or time.time() - float(db.kv_get(f"pub_last:{acct}", 0)) < gap * 60:
        return None
    return count


_ONLINE: dict[str, bool] = {}


def _online(p: dict, platform: str, s: dict) -> bool:
    """Mode GitHub : l'image du post est-elle déjà en ligne ? (sinon Buffer échouerait : on attend le passage suivant)"""
    if not s.get("public_static_url"):
        return True
    d = p["data"]
    rel = d.get("x_image") if platform in ("x", "hub") else (
        (d.get("tiktok_slides") or d.get("slides") or [""])[0] if platform == "tiktok" else (d.get("slides") or [""])[0])
    if not rel:
        return False
    url = f"{s['public_static_url'].rstrip('/')}/files/{rel}"
    if url not in _ONLINE:
        try:
            _ONLINE[url] = requests.head(url, timeout=10, allow_redirects=True).status_code == 200
        except requests.RequestException:
            _ONLINE[url] = False
    return _ONLINE[url]


def _pick(posts: list[dict], s: dict, platform: str, tag: str) -> dict | None:
    return next((p for p in posts if _eligible(p, s, platform) and not db.kv_get(f"pub_done:{p['id']}:{tag}")
                 and int(db.kv_get(f"pub_fail:{p['id']}:{tag}", 0)) < 2 and _online(p, platform, s)), None)


def _order(posts: list[dict]) -> list[dict]:
    """Les sujets chauds d'abord, puis les plus importants, puis les plus récents."""
    return sorted(posts, key=lambda p: (-bool(p["data"].get("hot")), -p["importance"], -p["created"]))


def autopublish_tick() -> None:
    """Appelé régulièrement : publie au plus un post par compte et par tour, au rythme propre à chaque réseau."""
    s = load_settings()
    cfg_all = s.get("publish") or {}
    hub = s.get("hub") or {}
    if not any(c.get("enabled") for c in cfg_all.values()) and not hub.get("enabled"):
        return
    _refresh_instagram_tokens(s)
    s = load_settings()
    cfg_all = s.get("publish") or {}
    medias = {m["id"]: m for m in load_medias(s)[0]}
    now = datetime.now(TZ)
    day, hour = now.strftime("%Y-%m-%d"), now.hour
    done: dict[int, dict] = {}          # article -> réseaux où il est parti pendant ce tour (1 notification par article)

    def ok(cand: dict, label: str) -> None:
        info = done.setdefault(cand["id"], {"name": medias[cand["media"]]["name"], "headline": cand["headline"], "labels": []})
        info["labels"].append(label)

    for media_id, cfg in cfg_all.items():
        if not cfg.get("enabled") or media_id not in medias:
            continue
        name = medias[media_id]["name"]
        posts = _order(db.posts(media_id, time.time() - 24 * 3600))
        for platform, label in PLATFORMS.items():
            route = _route(platform, cfg, s)
            if not route:
                continue
            cand = _pick(posts, s, platform, platform)
            if not cand:
                continue
            acct = f"{media_id}:{platform}"
            urgent = platform == "x" and bool(cand["data"].get("hot")) and cand["importance"] >= 8
            count = _ready(acct, platform, s, day, hour, urgent)
            if count is None:
                continue
            if _try(acct, label, name, cand, platform, cfg, s, route, platform, day, count):
                db.set_status(cand["id"], **({"posted_x": True} if platform == "x" else {"posted_social": True}))
                ok(cand, label)

    # Compte X généraliste « Gros Titre » : le meilleur des 5 médias, en continu (comme les grands comptes d'alertes)
    if hub.get("enabled") and hub.get("x") and buffer_ref(hub["x"], s)[0]:
        count = _ready("hub:x", "hub", s, day, hour)
        if count is not None:
            pool = sorted([p for p in db.posts(None, time.time() - 6 * 3600) if p["media"] in medias],
                          key=lambda p: (-gen(p), -bool(p["data"].get("hot")), -p["created"]))
            cand = _pick(pool, s, "hub", "hub")
            if cand and _try("hub:x", "X (Gros Titre)", hub.get("name") or "Gros Titre", cand, "x", {"x": hub["x"]}, s,
                             "buffer", "hub", day, count):
                ok(cand, f"X « {(hub.get('name') or 'Gros Titre').title()} »")
    _notify_published(done)
