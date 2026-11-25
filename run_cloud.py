"""Mode hébergé gratuit (GitHub Actions + GitHub Pages) : un passage complet puis arrêt.

Lancé toutes les 15 minutes par .github/workflows/studio.yml :
1) publie les posts prêts (Instagram / X) dont les images sont déjà en ligne sur GitHub Pages ;
2) relit l'actu, génère, vérifie, crée les visuels, lance les enquêtes ;
3) exporte la page des posts (site/) que GitHub Pages met en ligne.
Les clés viennent des « secrets » GitHub (variables d'environnement), jamais du dépôt.
"""
from __future__ import annotations

import html
import json
import os
import queue
import shutil
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from studio import db
from studio.config import CLOUD, POSTS, ROOT, load_medias, load_settings, save_settings, setup_logging

SITE = ROOT / "site"
PARIS = ZoneInfo("Europe/Paris")          # les serveurs de GitHub sont à l'heure UTC


def settings_from_env() -> None:
    """Réglages du mode hébergé. Les clés (secrets GitHub) sont lues en mémoire par studio.config et jamais
    écrites sur le disque. Par média : IG_<ID>_USER, IG_<ID>_TOKEN, X_<ID>_TOKEN, X_<ID>_SECRET (ID en majuscules)."""
    s = load_settings()
    pub = s.get("publish") or {}
    for m in load_medias(s)[0]:
        pub.setdefault(m["id"], {})["enabled"] = os.environ.get("AUTO_PUBLISH", "1") == "1"
    flag = lambda k: os.environ.get(k, "0") == "1"
    save_settings({"auto": True, "browser_reader": True, "keep_days": 3, "publish": pub,
                   "auto_sensitive": flag("AUTO_SENSITIVE"), "auto_enquetes": flag("AUTO_ENQUETES"),
                   "auto_judiciaire": os.environ.get("AUTO_JUDICIAIRE", "1") == "1"})


def run_cycle() -> None:
    import studio.engine as E
    from studio.publish import autopublish_tick

    s = load_settings()
    eng = E.Engine.__new__(E.Engine)
    db.init()
    eng.state, eng.lock, eng.q = {}, threading.Lock(), queue.Queue()
    autopublish_tick()                                   # images du passage précédent déjà en ligne
    hour = datetime.now(E.TZ).hour
    for idx, m in enumerate(load_medias(s)[0]):
        if not m.get("enabled", True):
            continue
        last_enq = float(db.kv_get(f"last_enquete:{m['id']}", 0))
        days = s.get("enquete_every_days", 3)
        if days > 0 and s.get("enquete_hour", 9) + idx <= hour < 23 and time.time() - last_enq >= days * 86400 - 3600:
            ok = eng.run_enquete(m["id"])
            db.kv_set(f"last_enquete:{m['id']}", time.time() if ok else time.time() - max(0, days - 1) * 86400)
        try:
            eng.run_media(m["id"], manual=False)
        except Exception as ex:
            print("Erreur", m["id"], ex)
        db.kv_set(f"last_check:{m['id']}", time.time())
    from studio.recap import run_recaps
    run_recaps(load_medias(s)[0], s)                     # « L'essentiel du jour » du soir


def export_site() -> None:
    """Page statique (lecture seule) : posts récents par média, images, textes à copier."""
    s = load_settings()
    medias = load_medias(s)[0]
    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "files").mkdir(parents=True)
    since = time.time() - s.get("keep_days", 3) * 86400
    blocks = []
    for m in medias:
        cards = []
        for p in db.posts(m["id"], since):
            d = p["data"]
            if p["hidden"]:
                continue
            files = list(d.get("slides", [])) + list(d.get("tiktok_slides", [])) + [d.get("x_image", "")]
            for rel in filter(None, files):
                dst = SITE / "files" / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                if (POSTS / rel).exists():
                    shutil.copy2(POSTS / rel, dst)
            v = (d.get("verif") or {}).get("verdict", "")
            badge = {"ok": "✅ vérifié", "corrige": "✏️ corrigé", "non_verifie": "⚠️ non vérifié"}.get(v, "")
            done = " · ".join(lbl for k, lbl in (("posted_x", "publié sur X"), ("posted_social", "publié Insta")) if p[k])
            slides = "".join(f'<a href="files/{html.escape(x)}" target="_blank"><img loading="lazy" src="files/{html.escape(x)}"></a>'
                             for x in d.get("slides", []))
            cards.append(f'''<article><div class="meta">{datetime.fromtimestamp(p["created"], PARIS).strftime("%d/%m %Hh%M")} · {badge}
              {" · ⚠️ sensible" if p["sensitive"] else ""}{" · " + done if done else ""}</div><h3>{html.escape(p["headline"])}</h3>
              <div class="slides">{slides}</div>
              <details><summary>Textes (description, tweet)</summary><pre>{html.escape(d.get("caption", ""))}</pre>
              <pre>{html.escape(d.get("x_text", ""))}</pre></details></article>''')
        blocks.append(f'<section id="{m["id"]}"><h2 style="color:{m["color"]}">{html.escape(m["name"])} '
                      f'<small>{html.escape(m["handle"])}</small></h2>{"".join(cards) or "<p>Aucun post récent.</p>"}</section>')
    nav = " ".join(f'<a href="#{m["id"]}">{html.escape(m["name"])}</a>' for m in medias)
    page = f'''<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>Studio Médias</title><style>
body{{margin:0;background:#0c0d12;color:#ececf3;font:15px/1.5 system-ui,sans-serif}}main{{max-width:1100px;margin:auto;padding:16px}}
nav{{position:sticky;top:0;background:#0c0d12ee;padding:10px 16px;border-bottom:1px solid #2a2b38}}nav a{{color:#ececf3;margin-right:14px}}
article{{background:#15161e;border:1px solid #2a2b38;border-radius:14px;padding:14px;margin:14px 0}}.meta{{color:#9b9cad;font-size:13px}}
.slides{{display:flex;gap:8px;overflow-x:auto}}.slides img{{height:260px;border-radius:10px}}pre{{white-space:pre-wrap;background:#0f1016;padding:10px;border-radius:10px}}
small{{color:#9b9cad;font-size:14px}}</style></head><body><nav>⚡ Studio Médias · mis à jour le {datetime.now(PARIS).strftime("%d/%m à %Hh%M")} (heure de Paris) · {nav}</nav>
<main>{"".join(blocks)}</main></body></html>'''
    (SITE / "index.html").write_text(page, encoding="utf-8")
    (SITE / ".nojekyll").write_text("", encoding="utf-8")


if __name__ == "__main__":
    if not CLOUD:
        raise SystemExit("run_cloud.py est fait pour GitHub Actions (STUDIO_CLOUD=1). Sur ton PC, lance LANCER.bat.")
    setup_logging()
    settings_from_env()
    run_cycle()
    export_site()
    print("Passage terminé")
