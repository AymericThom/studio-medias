"""Lecteur de pages avec un vrai navigateur (Chrome/Edge via Playwright), pour les sites qui refusent les robots.

Le navigateur ouvre l'article comme un lecteur normal (fenêtre placée hors de l'écran sous Windows,
mode invisible sur un serveur) et récupère le texte affiché. Règles :
- seulement ce qu'un visiteur non abonné voit : aucun contournement de paywall ;
- si le site affiche un CAPTCHA ou un blocage persistant, on abandonne cette page (aucune résolution de CAPTCHA) ;
- le texte sert uniquement à vérifier les faits ; il n'est ni stocké durablement ni republié.
"""
from __future__ import annotations

import logging
import os

from .config import DATA

log = logging.getLogger("studio.browser")
CHALLENGE = ("challenge", "access denied", "un instant", "just a moment", "attention required", "vérification",
             "are you a robot", "êtes-vous un robot", "captcha")
CAPTCHA_SEL = "iframe[src*='captcha'], iframe[src*='recaptcha'], iframe[src*='hcaptcha'], iframe[src*='datadome'], #px-captcha"


class PageReader:
    """À utiliser avec « with PageReader() as r: r.read(url) » ; démarre le navigateur une seule fois."""

    def __init__(self):
        self.pw = None
        self.ctx = None
        self.ok = False

    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            log.warning("Lecteur navigateur indisponible : installe-le avec  python -m pip install playwright")
            return self
        headless = os.name != "nt" and not os.environ.get("DISPLAY")
        args = ["--window-position=-32000,-32000", "--window-size=1280,900"]
        self.pw = sync_playwright().start()
        profile = DATA / "navigateur"
        for channel in ("chrome", "msedge", None):    # Chrome ou Edge déjà installés, sinon Chromium de Playwright
            try:
                kw = {"channel": channel} if channel else {}
                self.ctx = self.pw.chromium.launch_persistent_context(
                    str(profile), headless=headless, args=args, locale="fr-FR", viewport={"width": 1280, "height": 900}, **kw)
                self.ok = True
                log.info("Lecteur navigateur prêt (%s)", channel or "chromium")
                break
            except Exception as ex:
                log.debug("Navigateur %s indisponible : %s", channel, ex)
        if not self.ok:
            log.warning("Aucun navigateur trouvé : installe Chrome, ou lance  python -m playwright install chromium")
        return self

    def read(self, url: str, limit: int = 6000) -> str:
        if not self.ok or not url or "news.google." in url:
            return ""
        from .fulltext import _from_jsonld, _from_paragraphs

        page = self.ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(1500)
            for _ in range(8):   # laisse passer une vérification automatique (sans jamais résoudre de CAPTCHA)
                if not any(k in page.title().lower() for k in CHALLENGE):
                    break
                page.wait_for_timeout(1000)
            if any(k in page.title().lower() for k in CHALLENGE) or page.query_selector(CAPTCHA_SEL):
                log.info("Page protégée par un test anti-robot, ignorée : %s", url[:80])
                return ""
            html = page.content()
            text = _from_jsonld(html)
            if '"@context"' in text or "schema.org" in text:
                text = ""
            if len(text) < 400:
                alt = _from_paragraphs(html)
                if len(alt) > len(text):
                    text = alt
            return text[:limit] if len(text) >= 300 else ""
        except Exception as ex:
            log.debug("Lecture navigateur échouée %s : %s", url[:80], ex)
            return ""
        finally:
            try:
                page.close()
            except Exception:
                pass

    def __exit__(self, *exc):
        try:
            if self.ctx:
                self.ctx.close()
        finally:
            if self.pw:
                self.pw.stop()
        return False
