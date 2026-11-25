"""Crée le dossier COMPTES (à côté du studio) : pour chaque média, photo de profil, bannière X, bios et fiche « à faire ».
Relance-le si tu changes un nom ou une couleur :  python generer_comptes.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from studio.config import ROOT, load_medias
from studio.draw import emoji_sized, font, mix, rgb, text_w, vgradient

OUT = ROOT.parent / "COMPTES"

FICHES = {
    "politique": {
        "emoji": "🗳️",
        "tiktok": "La politique française, claire et vérifiée 🗳️ L'essentiel chaque jour",
        "insta": "🗳️ La politique française sans prise de tête\n📌 L'essentiel du jour en 3 images\n🔎 Une enquête chaque semaine\n✅ Infos vérifiées, sources citées",
        "x": "🗳️ L'actu politique française en continu. Rapide, clair, vérifié, sources citées. Enquêtes chaque semaine.",
        "suivre": "HugoDécrypte, franceinfo, Le Monde, BFMTV, Public Sénat, LCP, Le Parisien, Brut, Clément Viktorovitch",
        "heures": "7h30-9h (matinales), 12h-13h30, 18h-21h (QAG le mardi et mercredi après-midi)",
        "hashtags": "#politique #actu #assembleenationale #presidentielle2027 #france",
    },
    "finance": {
        "emoji": "💶",
        "tiktok": "Ton argent, l'éco du quotidien, en clair 💶 Prix, salaires, impôts",
        "insta": "💶 L'argent et l'éco du quotidien, en clair\n🛒 Prix, salaires, impôts, épargne, immobilier\n🔎 Une enquête chaque semaine\n✅ Sources citées · pas de conseil financier",
        "x": "💶 L'éco qui touche ton porte-monnaie : prix, salaires, impôts, épargne, entreprises. Clair et sourcé. Pas de conseil financier.",
        "suivre": "BFM Business, Les Échos, Capital, 60 Millions de consommateurs, UFC-Que Choisir, Finary, HugoDécrypte",
        "heures": "7h-9h, 12h-14h, 19h-21h (le dimanche soir marche bien pour l'épargne et l'immobilier)",
        "hashtags": "#argent #economie #pouvoirdachat #epargne #finance",
    },
    "tech": {
        "emoji": "🤖",
        "tiktok": "Tech et IA, l'essentiel sans jargon 🤖 Chaque jour",
        "insta": "🤖 La tech et l'IA, sans jargon\n📱 IA, smartphones, réseaux, jeux vidéo, cyber\n🔎 Une enquête chaque semaine\n✅ Sources citées",
        "x": "🤖 Tech & IA : l'essentiel de l'actu, sans jargon. IA, smartphones, réseaux sociaux, jeux vidéo, cybersécurité.",
        "suivre": "Underscore_, Frandroid, Numerama, Les Numériques, 01net, Micode, Siècle Digital, Le Monde Pixels",
        "heures": "8h-9h, 12h-14h, 18h-23h (le public tech est actif tard)",
        "hashtags": "#tech #ia #intelligenceartificielle #numerique #actutech",
    },
    "sport": {
        "emoji": "⚽",
        "tiktok": "Le sport qui fait parler ⚽ Foot, NBA, tennis, F1, chaque jour",
        "insta": "⚽ Le sport qui fait parler\n🏆 Ligue 1, Bleus, mercato, NBA, tennis, F1\n🔎 Une enquête chaque semaine\n✅ Infos vérifiées",
        "x": "⚽ L'actu sport en continu : Ligue 1, Bleus, mercato, NBA, tennis, F1. Rapide et vérifié.",
        "suivre": "L'Équipe, RMC Sport, Foot Mercato, Canal+ Sport, beIN Sports France, Eurosport, Winamax",
        "heures": "12h-14h, 18h-23h ; juste après les matchs et pendant le mercato",
        "hashtags": "#foot #sport #ligue1 #mercato #football",
    },
    "monde": {
        "emoji": "🌍",
        "tiktok": "Le monde expliqué simplement 🌍 Guerres, élections, crises",
        "insta": "🌍 Le monde, expliqué simplement\n🗺️ Géopolitique, conflits, élections, diplomatie\n🔎 Une enquête chaque semaine\n✅ Sources citées",
        "x": "🌍 L'actu internationale expliquée simplement : géopolitique, conflits, élections, diplomatie. Sources citées.",
        "suivre": "France 24, RFI, Courrier international, Le Monde, Arte (Le Dessous des cartes), Brut, HugoDécrypte",
        "heures": "7h-9h, 12h-14h, 18h-22h (et tout de suite quand une crise éclate)",
        "hashtags": "#monde #geopolitique #international #actu #news",
    },
}


# Le 6e compte, X seulement : le fil généraliste qui reprend le meilleur des 5 médias (Réglages > compte X généraliste)
HUB = {"id": "hub", "name": "GROS TITRE", "handle": "@grostitre", "color": "#DC2626", "accent": "#FACC15"}
HUB_FICHE = {
    "emoji": "🚨",
    "tiktok": "Les infos qui comptent, dès qu'elles tombent",
    "insta": "",
    "x": "🚨 Les infos qui comptent, dès qu'elles tombent. Politique, éco, tech, sport, monde. Vérifié, sources citées.",
    "epingle": ("🚨 Bienvenue sur Gros Titre : les infos qui comptent, dès qu'elles tombent, vérifiées et sourcées.\n\n"
                "Pour aller plus loin, suis nos comptes spécialisés :\n"
                "🗳️ Ballottage (politique)\n💶 La Fraîche (argent)\n🤖 Ctrl (tech et IA)\n"
                "⚽ Petit Pont (sport)\n🌍 Fuseau Horaire (monde)"),
}


def profile_picture(media: dict, size: int = 1080) -> Image.Image:
    c = rgb(media["color"])
    img = Image.new("RGBA", (size, size), (*c, 255))
    img.alpha_composite(vgradient(size, size, mix(c, (0, 0, 0), 0.5), 0, 170))
    words = media["name"].lower().split()
    lines = [" ".join(words[:1]), " ".join(words[1:])] if len(words) > 1 else [words[0]]
    s = 260
    while max(text_w(l, font("black", s)) for l in lines) > size * 0.74 and s > 60:
        s -= 6
    f = font("black", s)
    lh = int(s * 1.02)
    y0 = (size - lh * len(lines)) // 2 - int(s * 0.08)
    d = ImageDraw.Draw(img)
    for i, l in enumerate(lines):
        d.text((size // 2, y0 + i * lh + lh // 2), l, font=f, fill=(255, 255, 255), anchor="mm")
    bar_w = int(size * 0.18)
    by = y0 + lh * len(lines) + int(s * 0.12)
    d.rounded_rectangle(((size - bar_w) // 2, by, (size + bar_w) // 2, by + int(s * 0.09)), radius=12,
                        fill=rgb(media.get("accent", "#FFFFFF")))
    return img.convert("RGB")


def banner(media: dict, fiche: dict, w: int = 1500, h: int = 500) -> Image.Image:
    c = rgb(media["color"])
    img = Image.new("RGBA", (w, h), (*mix(c, (0, 0, 0), 0.15), 255))
    img.alpha_composite(vgradient(w, h, mix(c, (0, 0, 0), 0.6), 0, 200))
    d = ImageDraw.Draw(img)
    for r in range(120, 900, 60):                                  # cercles discrets derrière l'emoji
        d.ellipse((w - 330 - r, h // 2 - r, w - 330 + r, h // 2 + r), outline=(*mix(c, (255, 255, 255), 0.3), 35), width=2)
    e = emoji_sized(fiche["emoji"], 300)
    if e is not None:
        glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        glow.alpha_composite(e, (w - 330 - e.width // 2, h // 2 - e.height // 2))
        img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(28)))
        img.alpha_composite(e, (w - 330 - e.width // 2, h // 2 - e.height // 2))
    # sur X, la photo de profil recouvre le bas-gauche de la bannière : le texte reste en haut à gauche
    d.text((90, 80), media["name"].lower(), font=font("black", 104), fill=(255, 255, 255))
    tag = fiche["tiktok"].split(" 🗳️")[0].split(" 💶")[0].split(" 🤖")[0].split(" ⚽")[0].split(" 🌍")[0]
    d.text((94, 215), tag, font=font("semibold", 38), fill=(235, 235, 240))
    return img.convert("RGB")


def main() -> None:
    medias, _ = load_medias()
    OUT.mkdir(exist_ok=True)
    for m in medias:
        f = FICHES[m["id"]]
        folder = OUT / m["name"].title().replace("'", "")
        folder.mkdir(exist_ok=True)
        profile_picture(m).save(folder / "photo_de_profil.png")
        banner(m, f).save(folder / "banniere_x.png")
        handle = m["handle"]
        (folder / "bios.txt").write_text(
            f"NOM AFFICHÉ : {m['name'].title()}\nIDENTIFIANT : {handle}\n\n"
            f"--- TikTok (80 caractères max) ---\n{f['tiktok']}\n\n"
            f"--- Instagram (150 caractères max) ---\n{f['insta']}\n\n"
            f"--- X (160 caractères max) ---\n{f['x']}\n", encoding="utf-8")
        (folder / "A_FAIRE.md").write_text(f"""# {m['name'].title()} ({handle}) : ce que tu dois faire

Niche : {m['niche']}

## Jour 1 : créer les comptes
- [ ] **TikTok** : crée le compte {handle} avec une adresse e-mail dédiée, puis passe en « compte Pro » (Paramètres > Compte).
- [ ] **Instagram** : même identifiant, puis passe en compte **Professionnel > Créateur ou Entreprise**. C'est indispensable pour la publication automatique plus tard.
- [ ] **X** : même identifiant (si pris, ajoute `_fr`).
- [ ] Photo de profil : `photo_de_profil.png` (ce dossier). Bannière X : `banniere_x.png`.
- [ ] Bios : copie-les depuis `bios.txt` (une version par réseau, longueurs respectées).
- [ ] Crée les comptes **un ou deux par jour**, pas les 5 médias le même jour.

## Jours 1 à 5 : rendre le compte crédible
- [ ] 15 à 20 min par jour sur TikTok et Instagram : fais défiler ta niche, like, commente sincèrement quelques posts.
- [ ] Abonne-toi à : {f['suivre']}.
- [ ] Ne poste pas encore, ou au maximum 1 fois par jour.

## Dès le jour 4 ou 5 : publier
- [ ] 2 à 3 carrousels par jour au début, puis 3 à 5. Priorité aux 🔥 sujets chauds et aux 🔎 enquêtes.
- [ ] Meilleures heures : {f['heures']}.
- [ ] TikTok : mode photo, **son tendance à faible volume**, colle la description du studio.
- [ ] X : 5 à 10 tweets par jour avec leur image. Pour les enquêtes, publie le **fil complet**.
- [ ] Hashtags de base (le studio en propose déjà) : {f['hashtags']}.
- [ ] Réponds aux 10 premiers commentaires de chaque post.
- [ ] Sur X : réponds tôt et intelligemment sous les gros comptes de la niche.

## Chaque semaine
- [ ] Regarde quels posts ont le mieux marché (sujet, heure, accroche) et fais-en plus.
- [ ] Relis toujours les posts ⚠️ sensibles et ✏️ corrigés avant de publier.
""", encoding="utf-8")
        print(f"  {m['name']:16} -> {folder}")
    hub_identity()
    print(f"\nDossier : {OUT}")


def hub_identity() -> None:
    """Gros Titre : photo, bannière, bio, tweet épinglé et fiche « à faire » (compte X uniquement)."""
    folder = OUT / HUB["name"].title()
    folder.mkdir(exist_ok=True)
    profile_picture(HUB).save(folder / "photo_de_profil.png")
    banner(HUB, HUB_FICHE).save(folder / "banniere_x.png")
    (folder / "bios.txt").write_text(
        f"NOM AFFICHÉ : Gros Titre\nIDENTIFIANT : {HUB['handle']}  (vérifié libre sur X le 25/11/2026 ; sinon @grostitre_fr)\n\n"
        f"--- X (160 caractères max) ---\n{HUB_FICHE['x']}\n\n"
        f"--- Tweet à épingler (remplace les noms par les @ X de tes médias) ---\n{HUB_FICHE['epingle']}\n",
        encoding="utf-8")
    (folder / "A_FAIRE.md").write_text(f"""# Gros Titre ({HUB['handle']}) : le compte X généraliste du réseau

**Le rôle** : le fil des grosses infos des 5 médias (importance 8/10 et plus, ou sujet très chaud), en continu, comme les
grands comptes d'alertes. Sur X, ce sont eux qui grossissent le plus vite. Chaque post garde le visuel du média d'origine :
ça fait découvrir tes 5 comptes spécialisés. Compte **X uniquement** (pas d'Instagram ni de TikTok).

## Créer le compte (10 min)
- [ ] Sur X, crée le compte **{HUB['handle']}** (nom affiché : **Gros Titre**) avec une adresse e-mail dédiée.
- [ ] Photo de profil : `photo_de_profil.png`. Bannière : `banniere_x.png`. Bio : dans `bios.txt`.
- [ ] Publie le **tweet de bienvenue** (dans `bios.txt`), en remplaçant les noms par les @ X de tes médias, puis **épingle-le**.
- [ ] **Indique que le compte est automatisé** : Paramètres → Votre compte → Informations du compte → Automatisation,
      et choisis ton compte X principal comme gestionnaire. Un petit label « Automatisé » s'affiche : c'est ce que
      demandent les règles de X pour un compte qui publie tout seul, et ça réduit le risque de blocage.

## Le brancher au studio (5 min)
- [ ] Sur buffer.com, crée un **6e compte Buffer** gratuit et connectes-y ce compte X.
- [ ] Buffer : Settings → API → crée une clé.
- [ ] Studio : Réglages → Publication → colle la clé dans **Compte Buffer 6** → **Charger mes comptes Buffer**.
- [ ] Dans **⭐ Compte X généraliste** : coche **activer**, nom **GROS TITRE**, choisis le compte X → **Enregistrer**.
- [ ] Si le studio tourne sur GitHub : relance `METTRE_EN_LIGNE.bat`.

## Les premiers jours
- [ ] Les 3 premiers jours, réponds toi-même à quelques commentaires et suis les grands comptes d'actu
      (franceinfo, AFP, Le Monde, BFMTV, AlertesInfos…) pour que X comprenne le thème du compte.
- [ ] Par défaut : 30 posts par jour maximum, 12 min d'écart (réglable dans Réglages → Rythme de publication).
""", encoding="utf-8")
    print(f"  {'GROS TITRE':16} -> {folder}")


if __name__ == "__main__":
    sys.exit(main())
