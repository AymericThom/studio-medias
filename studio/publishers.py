"""Publication DIRECTE via les API officielles, sans limite de comptes (alternative à Buffer).

- Instagram : API officielle de Meta (« Instagram API with Instagram Login »), gratuite. Carrousels gérés.
  Pour tes propres comptes professionnels, pas besoin de validation de Meta (accès standard).
  Il faut que les images aient une adresse publique (studio hébergé, tunnel ou GitHub Pages).
- X : API officielle, payante à l'usage (environ 0,015 $ par post sans lien ; crédits offerts au départ).
  Une seule « app » développeur X publie sur tous tes comptes (un jeton par compte, obtenu avec un code PIN).
Doc : developers.facebook.com/docs/instagram-platform/content-publishing · docs.x.com
"""
from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger("studio.publishers")
IG = "https://graph.instagram.com"
X = "https://api.x.com"


class PublishError(RuntimeError):
    pass


# ------------------------------------------------------------------ Instagram
def _ig(method: str, path: str, token: str, **params) -> dict:
    try:
        r = requests.request(method, f"{IG}/{path}", params={**params, "access_token": token}, timeout=60)
    except requests.RequestException as ex:         # le message d'erreur contiendrait l'adresse avec le jeton
        raise PublishError(f"Instagram injoignable ({type(ex).__name__})") from None
    try:
        data = r.json()
    except Exception:
        raise PublishError(f"Instagram : réponse illisible (HTTP {r.status_code})")
    if "error" in data:
        raise PublishError(f"Instagram : {data['error'].get('message', data['error'])}")
    return data


def instagram_refresh(token: str) -> str:
    """Prolonge le jeton longue durée (60 jours). À appeler de temps en temps."""
    data = _ig("GET", "refresh_access_token", token, grant_type="ig_refresh_token")
    return data.get("access_token", token)


def instagram_publish(user_id: str, token: str, image_urls: list[str], caption: str) -> str:
    """Publie une image ou un carrousel (2 à 10 images). Retourne l'identifiant du post."""
    if not image_urls:
        raise PublishError("Instagram : aucune image")
    image_urls = image_urls[:10]
    if len(image_urls) == 1:
        creation = _ig("POST", f"{user_id}/media", token, image_url=image_urls[0], caption=caption)["id"]
    else:
        children = [_ig("POST", f"{user_id}/media", token, image_url=u, is_carousel_item="true")["id"] for u in image_urls]
        creation = _ig("POST", f"{user_id}/media", token, media_type="CAROUSEL", children=",".join(children),
                       caption=caption)["id"]
    for _ in range(20):          # Instagram prépare le média avant publication
        st = _ig("GET", creation, token, fields="status_code").get("status_code")
        if st in ("FINISHED", None):
            break
        if st == "ERROR":
            raise PublishError("Instagram a refusé le média (format ou image inaccessible)")
        time.sleep(3)
    return _ig("POST", f"{user_id}/media_publish", token, creation_id=creation)["id"]


# ------------------------------------------------------------------ X
def _x_session(api_key: str, api_secret: str, token: str = "", secret: str = "", **kw):
    from requests_oauthlib import OAuth1Session

    return OAuth1Session(api_key, client_secret=api_secret, resource_owner_key=token or None,
                         resource_owner_secret=secret or None, **kw)


def x_auth_start(api_key: str, api_secret: str) -> tuple[str, str, str]:
    """Étape 1 : retourne (lien d'autorisation, jeton temporaire, secret temporaire). Le compte X donne un code PIN."""
    s = _x_session(api_key, api_secret, callback_uri="oob")
    r = s.fetch_request_token(f"{X}/oauth/request_token")
    return f"{X}/oauth/authorize?oauth_token={r['oauth_token']}", r["oauth_token"], r["oauth_token_secret"]


def x_auth_finish(api_key: str, api_secret: str, tmp_token: str, tmp_secret: str, pin: str) -> dict:
    """Étape 2 : échange le code PIN contre le jeton permanent du compte."""
    s = _x_session(api_key, api_secret, tmp_token, tmp_secret, verifier=pin.strip())
    r = s.fetch_access_token(f"{X}/oauth/access_token")
    return {"token": r["oauth_token"], "secret": r["oauth_token_secret"], "screen_name": r.get("screen_name", "")}


def x_publish(api_key: str, api_secret: str, token: str, secret: str, text: str, image_path=None) -> str:
    s = _x_session(api_key, api_secret, token, secret)
    payload: dict = {"text": text}
    if image_path:
        with open(image_path, "rb") as f:
            r = s.post(f"{X}/2/media/upload", files={"media": f}, data={"media_category": "tweet_image"}, timeout=60)
        if r.status_code in (200, 201):
            j = r.json()
            mid = str(j.get("data", {}).get("id") or j.get("media_id_string") or "")
            if mid:
                payload["media"] = {"media_ids": [mid]}
        else:
            log.warning("X : image refusée (%s), tweet publié sans image", r.status_code)
    r = s.post(f"{X}/2/tweets", json=payload, timeout=30)
    if r.status_code not in (200, 201):
        raise PublishError(f"X a refusé le tweet ({r.status_code}) : {r.text[:200]}")
    return r.json()["data"]["id"]
