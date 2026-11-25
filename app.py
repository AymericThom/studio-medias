"""Studio Médias — le site-outil. Lance-le avec LANCER.bat (ou : python app.py), il s'ouvre dans ton navigateur."""
from __future__ import annotations

import base64
import hmac
import json
import mimetypes
import os
import shutil
import socket
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from studio import db
from studio.ai import Gemini, calls_today
from studio.config import BRAND, POSTS, RING, ROOT, WEB, load_medias, load_settings, mask, save_settings, setup_logging
from studio.engine import TZ, Engine, ensure_avatar, rerender
from studio.notify import send as notify_send, topic as notify_topic
from studio.publish import BUFFER_SLOTS, Buffer, BufferError, pub_token
from studio.publishers import x_auth_finish, x_auth_start
from studio import tunnel

PORT = 8765
ENGINE: Engine | None = None
EDITABLE = {"publish_rhythm", "hub", "recap", "recap_hour", "ai_quality", "auto", "check_every_min", "hot_sources", "min_gap_min", "max_silence_h", "hours", "per_run",
            "max_per_day", "carousel_size", "keep_days", "press_photo", "enquete_every_days", "enquete_hour", "browser_reader",
            "notify", "notify_ready", "notify_published", "notify_error", "publish", "publish_max_per_day",
            "publish_gap_min", "public_url", "tunnel", "auto_sensitive", "auto_enquetes", "public_static_url"}
X_PENDING: dict[str, tuple[str, str]] = {}   # connexion X en cours : media -> (jeton temporaire, secret)
STARTUP = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "StudioMedias.vbs"


def autostart(enabled: bool | None = None) -> bool:
    """Lance le studio en arrière-plan à l'ouverture de session Windows (raccourci dans le dossier Démarrage)."""
    if enabled is True:
        pyw = Path(sys.executable).with_name("pythonw.exe")
        exe = pyw if pyw.exists() else Path(sys.executable)
        cmd = f'CreateObject("WScript.Shell").Run """{exe}"" ""{ROOT / "app.py"}"" --no-browser", 0, False'
        STARTUP.parent.mkdir(parents=True, exist_ok=True)
        STARTUP.write_text(cmd + "\r\n", encoding="utf-16")
    elif enabled is False:
        STARTUP.unlink(missing_ok=True)
    return STARTUP.exists()


def safe_path(base: Path, rel: str) -> Path | None:
    p = (base / unquote(rel)).resolve()
    return p if base.resolve() in p.parents and p.is_file() else None


def state() -> dict:
    s = load_settings()
    medias, _ = load_medias(s)
    out = []
    for m in medias:
        ps = db.posts(m["id"], datetime.now(TZ).timestamp() - s.get("keep_days", 7) * 86400)
        todo = sum(1 for p in ps if not p["hidden"] and not (p["posted_x"] and p["posted_social"]))
        st = ENGINE.state.get(m["id"], {}) if ENGINE else {}
        out.append({k: m.get(k) for k in ("id", "name", "handle", "color", "accent", "cta", "niche", "enabled")}
                   | {"todo": todo, "total": len(ps), "status": st.get("status", "idle"), "msg": st.get("msg", ""),
                      "last": st.get("last", 0),
                      "version": f"{max([p['id'] for p in ps], default=0)}-{sum(p['data'].get('rev', 1) for p in ps)}"})
    pub = {k: s[k] for k in EDITABLE if k != "publish"}
    pub["publish"] = {mid: {"enabled": bool(c.get("enabled")), "ig_user_id": c.get("ig_user_id", ""),
                            "has_ig": bool(c.get("ig_token")), "has_x": bool(c.get("x_token")), "x_name": c.get("x_name", ""),
                            "x": c.get("x", ""), "instagram": c.get("instagram", ""), "tiktok": c.get("tiktok", "")}
                      for mid, c in (s.get("publish") or {}).items()}
    pub["has_x_app"] = bool(s.get("x_api_key") and s.get("x_api_secret"))
    pub.update(has_password=bool(s.get("password")),
               has_key=bool(s.get("gemini_key")), key_mask=mask(s.get("gemini_key", "")),
               has_pexels=bool(s.get("pexels_key")), pexels_mask=mask(s.get("pexels_key", "")),
               buffers=[{"n": i + 1, "has": bool(s.get(k)), "mask": mask(s.get(k, ""))} for i, k in enumerate(BUFFER_SLOTS)],
               autostart=autostart(), windows=os.name == "nt", has_buffer=any(s.get(k) for k in BUFFER_SLOTS),
               buffer_mask=mask(s.get("buffer_key", "")), ntfy_topic=notify_topic(), tunnel_status=tunnel.status())
    return {"settings": pub, "medias": out, "ai_calls": calls_today(), "log": list(RING.lines)[-40:],
            "busy": any(m["status"] != "idle" for m in out)}


def posts_for(media: str) -> list[dict]:
    s = load_settings()
    res = []
    for p in db.posts(media, datetime.now(TZ).timestamp() - s.get("keep_days", 7) * 86400):
        d = p["data"]
        res.append({
            "id": p["id"], "headline": p["headline"], "importance": p["importance"], "sensitive": bool(p["sensitive"]),
            "n_sources": p["n_sources"], "posted_x": bool(p["posted_x"]), "posted_social": bool(p["posted_social"]),
            "hidden": bool(p["hidden"]), "time": datetime.fromtimestamp(p["created"], TZ).strftime("%d/%m · %Hh%M"),
            "x_text": d.get("x_text", ""), "caption": d.get("caption", ""), "label": d.get("label", ""),
            "sources": d.get("sources", []), "credits": d.get("credits", []),
            "slides": [f"/files/{x}?v={d.get('rev', 1)}" for x in d.get("slides", [])],
            "x_image": f"/files/{d.get('x_image', '')}?v={d.get('rev', 1)}", "zip": f"/files/{d.get('zip', '')}",
            "can_rerender": "cover_text" in d, "press": bool(d.get("press")), "hot": bool(d.get("hot")),
            "news_time": d.get("news_time", p["created"]), "kind": d.get("kind", "actu"),
            "thread": d.get("thread", []), "verif": d.get("verif"),
            "tiktok_text": d.get("tiktok_text", ""), "tiktok_zip": f"/files/{d['tiktok_zip']}" if d.get("tiktok_zip") else "",
        })
    return res


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _file(self, p: Path | None, download: bool = False):
        if not p:
            return self._send(404, b"introuvable", "text/plain")
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        extra = {"Content-Disposition": f'attachment; filename="{p.name}"'} if download else None
        self._send(200, p.read_bytes(), ctype, extra)

    def _auth_ok(self) -> bool:
        """Si un mot de passe est défini dans Réglages, tout le site le demande (identifiant au choix)."""
        pw = load_settings().get("password", "")
        if not pw:
            return True
        h = self.headers.get("Authorization", "")
        if h.startswith("Basic "):
            try:
                given = base64.b64decode(h[6:]).decode("utf-8").split(":", 1)[-1]
                if hmac.compare_digest(given, pw):
                    return True
            except Exception:
                pass
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Studio Medias", charset="UTF-8"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        u = urlparse(self.path)
        if u.path.startswith("/pub/"):                      # images publiques signées (récupérées par Buffer)
            parts = u.path[5:].split("/", 1)
            if len(parts) == 2 and hmac.compare_digest(parts[0], pub_token(unquote(parts[1]))):
                return self._file(safe_path(POSTS, parts[1]))
            return self._send(404, b"introuvable", "text/plain")
        if not self._auth_ok():
            return
        q = parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            return self._file(WEB / "index.html")
        if u.path.startswith("/files/"):
            return self._file(safe_path(POSTS, u.path[7:]), download="dl" in q)
        if u.path.startswith("/brand/"):
            return self._file(safe_path(BRAND, u.path[7:]), download="dl" in q)
        if u.path == "/api/state":
            return self._json(state())
        if u.path == "/api/posts":
            return self._json(posts_for(q.get("media", [""])[0]))
        self._send(404, b"introuvable", "text/plain")

    def do_POST(self):
        if not self._auth_ok():
            return
        path, b = urlparse(self.path).path, self._body()
        if path == "/api/settings":
            upd = {k: v for k, v in b.items() if k in EDITABLE and k != "publish"}
            if isinstance(b.get("publish"), dict):
                cur = load_settings().get("publish") or {}
                for mid, f in b["publish"].items():
                    c = cur.setdefault(mid, {})
                    for k, v in f.items():
                        if k in ("ig_token",) and not str(v).strip():
                            continue                     # champ vide = garder le jeton enregistré
                        if k in ("enabled", "ig_user_id", "ig_token", "x", "instagram", "tiktok"):
                            c[k] = v.strip() if isinstance(v, str) else v
                upd["publish"] = cur
            for k in ("x_api_key", "x_api_secret"):
                if isinstance(b.get(k), str) and b[k].strip():
                    upd[k] = b[k].strip()
            for k in ("gemini_key", "pexels_key", "password", *BUFFER_SLOTS):
                if isinstance(b.get(k), str) and b[k].strip():
                    upd[k] = b[k].strip()
            if b.get("remove_password"):
                upd["password"] = ""
            if isinstance(b.get("medias"), dict):
                upd["medias"] = {mid: {k: v for k, v in f.items() if k in ("name", "handle", "color", "cta", "enabled")}
                                 for mid, f in b["medias"].items()}
            s_new = save_settings(upd)
            for m in load_medias()[0]:
                ensure_avatar(m)
            if s_new.get("tunnel") and s_new.get("password"):
                tunnel.start(int(os.environ.get("PORT", PORT)))
            elif not s_new.get("tunnel"):
                tunnel.stop()
            return self._json(state())
        if path == "/api/autostart":
            try:
                return self._json({"ok": True, "enabled": autostart(bool(b.get("enabled")))})
            except Exception as ex:
                return self._json({"ok": False, "msg": str(ex)})
        if path == "/api/x/start":
            st = load_settings()
            try:
                url, tok, sec = x_auth_start(st.get("x_api_key", ""), st.get("x_api_secret", ""))
                X_PENDING[b.get("media", "")] = (tok, sec)
                return self._json({"ok": True, "url": url})
            except Exception as ex:
                return self._json({"ok": False, "msg": f"Connexion X impossible : {ex}"})
        if path == "/api/x/finish":
            st, mid = load_settings(), b.get("media", "")
            if mid not in X_PENDING:
                return self._json({"ok": False, "msg": "Recommence : clique d'abord sur « Connecter X »"})
            try:
                res = x_auth_finish(st["x_api_key"], st["x_api_secret"], *X_PENDING.pop(mid), b.get("pin", ""))
                cur = st.get("publish") or {}
                cur.setdefault(mid, {}).update(x_token=res["token"], x_secret=res["secret"], x_name=res["screen_name"])
                save_settings({"publish": cur})
                return self._json({"ok": True, "name": res["screen_name"]})
            except Exception as ex:
                return self._json({"ok": False, "msg": f"Code refusé : {ex}"})
        if path == "/api/notify-test":
            ok = notify_send("🧪 Studio Médias", "Test réussi : tu recevras ici les posts prêts, publiés et les erreurs.",
                             ["test_tube"], kind="ready")
            return self._json({"ok": ok, "topic": notify_topic()})
        if path == "/api/buffer/channels":
            s, typed = load_settings(), b.get("keys") or []
            chans, errs = [], []
            for i, slot in enumerate(BUFFER_SLOTS):
                key = (typed[i] if i < len(typed) and isinstance(typed[i], str) else "").strip() or s.get(slot, "")
                if not key:
                    continue
                try:
                    chans += [{**c, "account": i + 1, "ref": f"{i + 1}:{c['id']}"} for c in Buffer(key).channels()]
                except Exception as ex:
                    errs.append(f"Buffer {i + 1} : {ex}")
            if not chans and errs:
                return self._json({"ok": False, "msg": " · ".join(errs)})
            if not chans:
                return self._json({"ok": False, "msg": "Colle au moins une clé Buffer"})
            return self._json({"ok": True, "channels": chans, "warn": " · ".join(errs)})
        if path == "/api/test-key":
            key = (b.get("key") or "").strip() or load_settings().get("gemini_key", "")
            ok, msg = Gemini(key, load_settings().get("ai_quality", "eco")).test()
            return self._json({"ok": ok, "msg": msg})
        if path == "/api/enquete":
            return self._json({"started": ENGINE.request(b.get("media", ""), manual=True, task="enquete")})
        if path == "/api/generate":
            target = b.get("media", "all")
            medias = [m for m in load_medias()[0] if m.get("enabled", True)]
            ids = [m["id"] for m in medias] if target == "all" else [target]
            started = [i for i in ids if ENGINE.request(i, manual=True)]
            return self._json({"started": started})
        if path.startswith("/api/post/"):
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[2].isdigit():
                pid, action = int(parts[2]), parts[3]
                if action == "status":
                    db.set_status(pid, **b)
                    return self._json({"ok": True})
                if action == "rerender":
                    return self._json({"ok": rerender(pid)})
                if action == "delete":
                    p = db.delete_post(pid)
                    if p:
                        d = (POSTS / p["data"].get("dir", "__none__")).resolve()
                        if POSTS.resolve() in d.parents:
                            shutil.rmtree(d, ignore_errors=True)
                    return self._json({"ok": True})
        self._send(404, b"introuvable", "text/plain")


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))   # aucun paquet envoyé
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def main():
    global ENGINE
    setup_logging()
    ENGINE = Engine()
    try:
        srv = ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", PORT))), Handler)
    except OSError:
        print(f"\n  Le port {PORT} est déjà utilisé : le studio est sans doute déjà ouvert -> http://localhost:{PORT}\n")
        webbrowser.open(f"http://localhost:{PORT}")
        return
    print("\n  ==============================================")
    print("   STUDIO MÉDIAS est lancé")
    print(f"   Sur ce PC        : http://localhost:{PORT}")
    print(f"   Sur ton téléphone: http://{lan_ip()}:{PORT}  (même Wi-Fi)")
    print("   Laisse cette fenêtre ouverte. Ferme-la pour arrêter.")
    print("  ==============================================\n")
    s0 = load_settings()
    if s0.get("tunnel") and s0.get("password"):
        tunnel.start(int(os.environ.get("PORT", PORT)))
    if "--no-browser" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
