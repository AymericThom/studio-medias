"""Gemini (palier gratuit) : UN seul appel par média et par passage choisit les sujets ET rédige tout."""
from __future__ import annotations

import json
import logging
import re
import time

import requests

from . import db
from .humanize import STYLE, humanize

log = logging.getLogger("studio.ai")
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MODELS = {
    "eco": ["gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-3.1-flash-lite",
            "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.8-flash", "gemini-flash-latest", "gemini-3-flash-preview",
            "gemini-2.5-flash", "gemini-4-hydrogen"],
    "max": ["gemini-3.6-flash", "gemini-3.8-flash", "gemini-3.5-flash", "gemini-flash-latest",
            "gemini-3.5-flash-lite", "gemini-flash-lite-latest"],
}
STRONG_SENSITIVE = ["attentat", "terroris", "viol", "meurtre", "assassinat", "suicide", "otage", "fusillade",
                    "pédo", "mineur", "infanticide", "féminicide", "agression sexuelle"]

CHARTE = """CHARTE (obligatoire) :
- Utilise UNIQUEMENT les faits présents dans les extraits. N'invente jamais un chiffre, un nom, une date ou une citation.
- Info rapportée par une seule source ou non confirmée : conditionnel + « selon <média> ».
- Présomption d'innocence (« mis en cause », « suspecté »). Jamais le nom d'un mineur ou d'une victime anonyme.
- Ton neutre, factuel, sans opinion ni sensationnalisme trompeur.
- Reformule avec tes propres mots : ne recopie jamais une phrase des extraits.
- Aucune URL, aucun nom de domaine, aucune @mention.
- Français impeccable."""


class AIError(RuntimeError):
    pass


_BACKOFF: dict[str, float] = {}   # modèle -> heure jusqu'à laquelle on ne l'essaie plus (partagé entre les passages)


def _pause(model: str, seconds: float) -> None:
    _BACKOFF[model] = time.time() + seconds


class Gemini:
    def __init__(self, key: str, quality: str = "eco"):
        self.key = (key or "").strip()
        self.models = MODELS.get(quality, MODELS["eco"])

    def call(self, system: str, prompt: str, temperature: float = 0.6):
        if not self.key:
            raise AIError("Aucune clé Gemini : ajoute-la dans Réglages.")
        last = "aucun modèle disponible"
        overloaded = 0
        for model in self.models:
            if overloaded >= 3:
                raise AIError("Gemini est saturé en ce moment : nouvel essai automatique dans 10 min")
            if _BACKOFF.get(model, 0) > time.time():
                continue
            for attempt in range(2):
                try:
                    r = requests.post(API.format(model=model), timeout=120,
                                      headers={"x-goog-api-key": self.key, "Content-Type": "application/json"},
                                      json={"systemInstruction": {"parts": [{"text": system}]},
                                            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                                            "generationConfig": {"temperature": temperature,
                                                                 "responseMimeType": "application/json"}})
                except requests.RequestException as ex:
                    last = str(ex)
                    time.sleep(3)
                    continue
                _count_call()
                if r.status_code == 200:
                    parts = (r.json().get("candidates") or [{}])[0].get("content", {}).get("parts", [])
                    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
                    try:
                        data = _json(text)
                        log.info("IA : réponse de %s", model)
                        return data
                    except Exception:
                        last = f"{model} : réponse illisible"
                        continue
                body = r.text[:300]
                if r.status_code in (400, 401, 403) and ("API key" in body or "PERMISSION" in body):
                    raise AIError("Clé Gemini refusée : vérifie-la dans Réglages.")
                if r.status_code == 429:
                    m = re.search(r'"retryDelay":\s*"(\d+)', r.text)
                    wait = int(m.group(1)) if m else 0
                    if attempt == 0 and 0 < wait <= 45:          # limite par minute : on patiente
                        log.info("IA : limite par minute sur %s, pause %ss", model, wait)
                        time.sleep(wait + 1)
                        continue
                    log.info("IA : quota atteint sur %s, modèle suivant", model)
                    _pause(model, 600 if wait else 6 * 3600)
                    last = f"quota atteint ({model})"
                    break
                if r.status_code in (404, 400):
                    _pause(model, 24 * 3600)
                    last = f"{model} indisponible"
                    break
                last = f"{model} HTTP {r.status_code}"     # 500/503 : surcharge -> on réessaie puis modèle suivant
                if attempt == 1:
                    log.info("IA : %s surchargé, modèle suivant pour 2 min", model)
                    _pause(model, 120)
                    overloaded += 1
                time.sleep(8)        # patience avant de réessayer le même modèle
        raise AIError(f"Gemini n'a pas répondu ({last}). Réessaie plus tard.")

    def test(self) -> tuple[bool, str]:
        try:
            self.call("Réponds en JSON.", 'Réponds exactement {"ok": true}', 0)
            return True, "Clé valide ✔"
        except AIError as ex:
            return False, str(ex)


def _count_call() -> None:
    day = time.strftime("%Y-%m-%d")
    db.kv_set(f"ai_calls:{day}", int(db.kv_get(f"ai_calls:{day}", 0)) + 1)


def calls_today() -> int:
    return int(db.kv_get(f"ai_calls:{time.strftime('%Y-%m-%d')}", 0))


def _json(text: str):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        a, b = text.find("{"), text.rfind("}")
        return json.loads(text[a:b + 1])


def _age(ts: float) -> str:
    m = max(0, int((time.time() - ts) / 60))
    return f"il y a {m} min" if m < 60 else f"il y a {m // 60} h"


def _block(c: dict, sid: str) -> str:
    lines = [f"[{sid}] {c['n_sources']} média(s) : {', '.join(c['sources'][:8])} · dernier article {_age(c['latest'])}"]
    seen = set()
    for a in sorted(c["articles"], key=lambda a: -a["weight"]):
        if a["title"] in seen or len(seen) >= 5:
            continue
        seen.add(a["title"])
        summ = f" — {a['summary'][:320]}" if a.get("summary") else ""
        lines.append(f"  • {a['source']} ({_age(a['published'])}) : {a['title']}{summ}")
    return "\n".join(lines)


def write_posts(gem: Gemini, media: dict, clusters: list[dict], recent: list[str], n: int,
                others: list[str] | None = None, other_niches: list[str] | None = None,
                rubriques: dict[str, int] | None = None) -> list[dict]:
    if not clusters or n <= 0:
        return []
    ids = {f"S{i + 1}": c for i, c in enumerate(clusters)}
    system = f"""Tu es le rédacteur en chef de « {media['name']} », un média d'information sur Instagram, TikTok et X,
spécialisé dans {media['niche']}. Public : {media['audience']}.
Nous sommes le {time.strftime('%d/%m/%Y')}. Ne traite QUE des faits nouveaux d'aujourd'hui : ignore un article qui revient
sur un événement ancien, une analyse de fond sans fait nouveau, ou un « ce qu'il faut savoir » sur un sujet déjà connu.
{CHARTE}
{STYLE}

Pour chaque sujet retenu, tu produis :
1) POST X (texte + 1 photo) : « <drapeau emoji du pays concerné> <ÉTIQUETTE> - <une à deux phrases denses qui donnent l'info,
   ses acteurs et son enjeu> (via <média source principal>). » ÉTIQUETTE : FLASH (info qui vient de tomber), ALERTE (danger
   ou urgence pour le public), OFFICIEL (UNIQUEMENT une décision ou annonce formelle d'une institution : gouvernement,
   loi, justice, club, entreprise ; jamais une déclaration ou une critique), sinon INFO. 270 caractères maximum, pas de hashtag.
2) CARROUSEL Instagram/TikTok de 3 images :
   - image 1 : « label » = bandeau court en majuscules (DERNIÈRE MINUTE si l'info vient de tomber, sinon le thème précis,
     ex. PRÉSIDENTIELLE 2027, POUVOIR D'ACHAT, INTELLIGENCE ARTIFICIELLE, LIGUE 1, GUERRE EN UKRAINE) + « label_emoji » (1 emoji
     adapté : 🚨 DERNIÈRE MINUTE, 🗳️ élections, 🏛️ institutions, ⚖️ justice, 💶 argent, 📈 bourse, 🏠 logement,
     🤖 IA, 📱 tech, 🎮 jeux vidéo, ⚽ foot, 🏀 basket, 🏉 rugby, 🎾 tennis, 🏎️ F1, 🌍 monde, 🇺🇸 États-Unis, 🕊️ paix) + « cover_text » = LA phrase qui résume l'info, 25 à 45 mots, complète et précise.
   - image 2 : « points_title » (12 à 24 mots, annonce la liste, peut finir par ⬇️) + « points » : 3 à 6 éléments courts
     (4 à 20 mots) = faits clés, chiffres, réactions, conséquences ; 1 à 3 mots importants en **gras** par élément.
   - image 3 : appel à s'abonner (ajouté automatiquement).
   - « caption » : la description du post, 5 à 8 paragraphes courts séparés par une ligne vide (140 à 240 mots).
     La 1re phrase donne l'info principale (c'est elle qu'on voit avant « plus »). Puis : détails concrets, réactions
     attribuées (« selon… », « a déclaré… »), contexte utile, et ce qui va se passer. 1 ou 2 paragraphes peuvent
     commencer par 👉. Ton d'un journaliste qui raconte, pas d'un communiqué.
   - « hashtags » : 3 à 5 hashtags pertinents.
   - « question » : une question courte et ouverte (6 à 14 mots), en TUTOYANT, précise et liée au sujet, qui donne envie de commenter
     (ex. « Tu trouves cette mesure juste ? », « Qui sort gagnant de ce duel ? »). Jamais « Et vous, qu'en pensez-vous ? ».
     Chaîne vide si le sujet parle de morts, de victimes, de drame ou s'il est sensible.
   - « rubrique » : la rubrique du sujet, choisie dans cette liste : {", ".join(media.get("rubriques", [])) or "libre"}."""
    prompt = ("Sujets candidats (articles regroupés automatiquement) :\n\n"
              + "\n\n".join(_block(c, sid) for sid, c in ids.items())
              + "\n\nDéjà publiés récemment par ce média (ne refais pas ces sujets) :\n"
              + ("\n".join(f"- {t}" for t in recent[:25]) or "- aucun")
              + "\n\nDéjà publiés par les autres médias du groupe (ne les reprends pas) :\n"
              + ("\n".join(f"- {t}" for t in (others or [])[:30]) or "- aucun")
              + "\n\nLes autres médias du groupe couvrent : " + " ; ".join(other_niches or [])
              + ". Un sujet qui relève clairement de leur niche (ex. un match de foot pour un média monde) n'est PAS pour toi."
              + ("\n\nRubriques déjà traitées aujourd'hui : " + ", ".join(f"{k} {v}" for k, v in (rubriques or {}).items())
                 + ". À intérêt égal, préfère une rubrique peu traitée : un compte qui varie ses sujets garde mieux ses"
                 " abonnés. Mais ne prends jamais un sujet faible juste pour varier." if rubriques else "")
              + f"""

Choisis au maximum {n} sujet(s) : les MEILLEURS pour {media['name']}.
HORS SUJET pour {media['name']} (ne les prends JAMAIS) : {media.get('exclude', 'tout ce qui sort de la niche')}.
Un bon sujet pour les réseaux : on s'arrête de scroller (surprenant, chiffre frappant, grand nom, décision qui change le
quotidien, polémique sourcée), on a envie de commenter ou de partager, et c'est au cœur de la niche.
Écarte aussi la pub, les bons plans, les tests produits, les directs sans fait nouveau et les doublons.
Note chaque sujet : « pertinence_niche » (1-10 : est-ce vraiment le cœur de la niche ?) et « potentiel_reseaux »
(1-10 : est-ce que ça va faire réagir sur TikTok, Instagram et X ?). Ne retourne QUE les sujets notés au moins 7 sur les deux.
S'il n'y a rien de bon, renvoie une liste vide : mieux vaut aucun post qu'un post moyen.

Réponds en JSON :
{{"posts": [{{
  "id": "S1", "importance": 1-10, "sensitive": true/false, "pertinence_niche": 1-10, "potentiel_reseaux": 1-10,
  "headline": "titre interne factuel ≤ 90 caractères",
  "x_text": "...", "label": "...", "label_emoji": "...", "cover_text": "...",
  "points_title": "...", "points": ["...", "..."], "caption": "...", "hashtags": ["#..."], "question": "...", "rubrique": "...",
  "image_subjects": ["nom exact de la personne (ou du lieu, de l'institution) principale, tel que le titre de sa page Wikipédia EN FRANÇAIS", "2e personne seulement si elle est centrale"],
  "image_query_en": "2 à 4 mots en anglais pour une photo d'illustration"
}}]}}
« sensitive » = true si : morts ou blessés graves, terrorisme, mineurs, accusation ou procédure judiciaire visant une personne nommée, scandale sanitaire, rumeur non confirmée. (Une blessure de sportif n'est PAS sensible.)"""
              )
    data = gem.call(system, prompt)
    out = []
    for p in (data.get("posts") if isinstance(data, dict) else data) or []:
        c = ids.get(str(p.get("id", "")).strip())
        if not c or not p.get("cover_text") or not p.get("x_text"):
            continue
        try:
            fit_n, buzz = int(p.get("pertinence_niche", 7)), int(p.get("potentiel_reseaux", 7))
        except (TypeError, ValueError):
            fit_n, buzz = 7, 7
        if fit_n < 7 or buzz < 6:
            log.info("Sujet écarté au tri (niche %s/10, réseaux %s/10) : %s", fit_n, buzz, p.get("headline", ""))
            continue
        points = [str(x).strip() for x in (p.get("points") or []) if str(x).strip()][:6]
        if len(points) < 2:
            continue
        titles = " ".join(a["title"] for a in c["articles"]).lower()
        try:
            importance = int(p.get("importance", 5))
        except (TypeError, ValueError):
            importance = 5
        out.append({
            "cluster": c,
            "importance": max(1, min(10, importance)),
            "sensitive": bool(p.get("sensitive")) or any(w in titles for w in STRONG_SENSITIVE),
            "headline": str(p.get("headline") or c["title"])[:110],
            "x_text": humanize(str(p["x_text"]).strip()),
            "label": str(p.get("label") or "INFO").strip()[:34],
            "label_emoji": str(p.get("label_emoji") or "").strip()[:4],
            "cover_text": humanize(str(p["cover_text"]).strip()),
            "points_title": humanize(str(p.get("points_title") or "Ce qu'il faut savoir ⬇️").strip()),
            "points": [humanize(x) for x in points],
            "caption": humanize(str(p.get("caption") or "").strip()),
            "hashtags": [h if str(h).startswith("#") else f"#{h}" for h in (p.get("hashtags") or [])][:5],
            "question": humanize(str(p.get("question") or "").strip())[:120],
            "rubrique": str(p.get("rubrique") or "").strip()[:40],
            "image_subjects": [str(s).strip() for s in (p.get("image_subjects") or []) if str(s).strip()][:2],
            "image_query_en": str(p.get("image_query_en") or ""),
        })
    return out[:n]


# ------------------------------------------------------------------ vérification des faits
VERIF_SYSTEM = """Tu es le vérificateur (fact-checker) d'une rédaction. Ton travail : empêcher toute désinformation.
Tu reçois un post prêt à publier et le TEXTE COMPLET de plusieurs articles de presse sur le même sujet.
Pour CHAQUE affirmation factuelle du post (noms, fonctions, chiffres, dates, lieux, citations, causes, conséquences) :
- elle est confirmée par au moins un article -> garde-la ;
- un article dit autre chose -> corrige-la ;
- aucun article ne la soutient -> supprime-la ou reformule-la prudemment ;
- les articles se contredisent -> conditionnel et attribution (« selon X »).
N'ajoute AUCUNE information absente des articles. Garde le style, la longueur et la structure du post.
Si le fait principal du post n'est soutenu par aucun article, verdict « rejete ».
Photo : on te dit quelle page Wikipédia a fourni la photo. Si ce n'est PAS la personne, le lieu ou l'organisation au cœur
du sujet (homonyme, mauvaise personne, sujet sans rapport), photo_ok = false."""


def verify_post(gem: Gemini, post: dict, texts: list[dict], photo_info: str = "") -> dict:
    """Retourne {verdict: ok|corrige|rejete|non_verifie, problemes: [...], + champs corrigés, photo_ok}."""
    if not texts:
        return {"verdict": "non_verifie", "problemes": ["Articles complets inaccessibles : vérifié seulement sur les résumés"],
                "photo_ok": True}
    docs = "\n\n".join(f"=== Article {i + 1} ({t['source']}) : {t['title']}\n{t['text'][:3500]}" for i, t in enumerate(texts[:3]))
    draft = {k: post.get(k) for k in ("x_text", "cover_text", "points_title", "points", "caption")}
    prompt = (f"ARTICLES :\n{docs}\n\nPOST À VÉRIFIER (JSON) :\n{json.dumps(draft, ensure_ascii=False)}\n\n"
              f"PHOTO : {photo_info or 'photo de presse ou d’illustration, rien à vérifier'}\n\n"
              """Réponds en JSON : {"verdict": "ok" | "corrige" | "rejete",
"problemes": ["chaque erreur trouvée et ce que tu as fait, en une phrase courte ; liste vide si tout est juste"],
"x_text": "...", "cover_text": "...", "points_title": "...", "points": ["..."], "caption": "...",
"photo_ok": true/false}
Renvoie TOUS les champs du post, corrigés si besoin (identiques si tout est juste).""")
    data = gem.call(VERIF_SYSTEM, prompt, temperature=0.1)
    if not isinstance(data, dict):
        raise AIError("Réponse du vérificateur illisible")
    out = {"verdict": str(data.get("verdict", "ok")).lower().replace("é", "e"),
           "problemes": [str(x) for x in (data.get("problemes") or [])][:8],
           "photo_ok": bool(data.get("photo_ok", True))}
    for k in ("x_text", "cover_text", "points_title", "caption"):
        if isinstance(data.get(k), str) and data[k].strip():
            out[k] = humanize(data[k].strip())
    if isinstance(data.get("points"), list) and len([p for p in data["points"] if str(p).strip()]) >= 2:
        out["points"] = [humanize(str(p).strip()) for p in data["points"] if str(p).strip()][:6]
    if out["verdict"] not in ("ok", "corrige", "rejete"):
        out["verdict"] = "ok"
    return out
