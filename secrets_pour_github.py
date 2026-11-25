"""Liste les secrets à mettre dans GitHub (clé Gemini, Buffer, comptes, sujet ntfy), lus dans ton studio local.

Utilisé par installer_github.py (qui les envoie tout seul, chiffrés, dans ton dépôt).
Lancé seul (python secrets_pour_github.py), il les AFFICHE pour une installation à la main.
Rien n'est envoyé nulle part. Ne copie jamais ce résultat ailleurs que dans les secrets GitHub.
"""
from studio.config import load_settings

GLOBAL = (("GEMINI_API_KEY", "gemini_key"), ("NTFY_TOPIC", "ntfy_topic"), ("PEXELS_API_KEY", "pexels_key"),
          ("X_API_KEY", "x_api_key"), ("X_API_SECRET", "x_api_secret"), ("BUFFER_KEY_1", "buffer_key"),
          ("BUFFER_KEY_2", "buffer_key2"), ("BUFFER_KEY_3", "buffer_key3"), ("BUFFER_KEY_4", "buffer_key4"),
          ("BUFFER_KEY_5", "buffer_key5"), ("BUFFER_KEY_6", "buffer_key6"))


def collect() -> list[tuple[str, str]]:
    s = load_settings()
    out = [(nom, s[cle]) for nom, cle in GLOBAL if s.get(cle)]
    for mid, c in (s.get("publish") or {}).items():
        M = mid.upper()
        for nom, cle in ((f"IG_{M}_USER", "ig_user_id"), (f"IG_{M}_TOKEN", "ig_token"),
                         (f"X_{M}_TOKEN", "x_token"), (f"X_{M}_SECRET", "x_secret"), (f"BUFFER_{M}_X", "x"),
                         (f"BUFFER_{M}_TIKTOK", "tiktok"), (f"BUFFER_{M}_INSTAGRAM", "instagram")):
            if c.get(cle):
                out.append((nom, str(c[cle])))
    hub = s.get("hub") or {}
    if hub.get("enabled") and hub.get("x"):
        out.append(("BUFFER_HUB_X", hub["x"]))
    return out


if __name__ == "__main__":
    lignes = collect()
    if not lignes:
        print("Aucun secret enregistré pour l'instant (renseigne d'abord les Réglages du studio).")
    for nom, val in lignes:
        print(f"\nNom    : {nom}\nValeur : {val}")
