"""Adresse publique automatique du studio via un tunnel Cloudflare (gratuit, aucun port à ouvrir, aucun compte).

Utile pour que Buffer (et ton téléphone, de partout) accède au studio. Il faut avoir installé « cloudflared »
une fois :  winget install --id Cloudflare.cloudflared
Le tunnel ne démarre que si un mot de passe protège le site ; les images publiées passent par des liens signés.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import threading
from pathlib import Path

log = logging.getLogger("studio.tunnel")
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
_state = {"url": "", "proc": None, "error": ""}


def find_cloudflared() -> str | None:
    for cand in (shutil.which("cloudflared"), r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
                 r"C:\Program Files\cloudflared\cloudflared.exe"):
        if cand and Path(cand).exists():
            return cand
    return None


def current_url() -> str:
    p = _state["proc"]
    return _state["url"] if p is not None and p.poll() is None else ""


def status() -> dict:
    return {"url": current_url(), "error": _state["error"], "installed": bool(find_cloudflared())}


def start(port: int = 8765) -> None:
    """Lance le tunnel en arrière-plan (sans bloquer) ; l'adresse apparaît dans les journaux et dans Réglages."""
    if current_url() or (_state["proc"] is not None and _state["proc"].poll() is None):
        return
    exe = find_cloudflared()
    if not exe:
        _state["error"] = "cloudflared n'est pas installé (winget install --id Cloudflare.cloudflared)"
        log.warning("Tunnel : %s", _state["error"])
        return

    def run():
        try:
            flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            proc = subprocess.Popen([exe, "tunnel", "--no-autoupdate", "--url", f"http://localhost:{port}"],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=flags)
            _state.update(proc=proc, error="")
            for line in proc.stdout:
                m = URL_RE.search(line)
                if m and not _state["url"]:
                    _state["url"] = m.group(0)
                    log.info("Adresse publique du studio : %s", _state["url"])
            _state["url"] = ""
            log.warning("Le tunnel Cloudflare s'est arrêté")
        except Exception as ex:
            _state["error"] = str(ex)
            log.warning("Tunnel impossible : %s", ex)

    threading.Thread(target=run, daemon=True).start()


def stop() -> None:
    p = _state["proc"]
    if p is not None and p.poll() is None:
        p.terminate()
    _state.update(url="", proc=None)
