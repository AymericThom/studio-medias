"""Rend les textes moins « IA » : consignes de style pour Gemini + nettoyage automatique après coup.

Tics repérés par les guides « humaniser un texte IA » (Blog du Modérateur, Jedha, QuillBot, Sherpas…) :
connecteurs creux, formules toutes faites, verbes « corporate », tiret cadratin, rythme trop régulier.
"""
from __future__ import annotations

import re

STYLE = """STYLE HUMAIN (très important : le texte doit sonner comme un journaliste, pas comme une IA) :
- Entre directement dans le fait. Pas d'introduction, pas de conclusion qui résume.
- Alterne phrases très courtes et phrases plus longues. Mots simples du quotidien.
- Des faits concrets : qui, quoi, combien, quand. Pas de généralités.
- JAMAIS de tiret cadratin (—) ni de tiret demi-cadratin (–) : utilise une virgule, deux-points ou un point.
- Pas de structure « ce n'est pas X, c'est Y », pas de question suivie de sa réponse, pas de liste de trois par réflexe.
- Mots et tournures INTERDITS : en outre, de plus, par ailleurs, ainsi, néanmoins, toutefois, dès lors, en effet,
  notamment, à cet égard, en somme, en bref, en conclusion, il convient de, il est important de, force est de constater,
  il s'agit de, joue un rôle (clé/crucial/majeur), crucial, primordial, incontournable, essentiel, véritable,
  souligne, met en lumière, met en exergue, témoigne de, s'inscrit dans, dans un contexte de, à l'heure où,
  révolutionner, plonger, naviguer, écosystème, considérablement, significativement, un tournant, une nouvelle ère,
  sans précédent (sauf fait vérifié), de taille, de mise, n'a pas manqué de.
- Clichés de presse INTERDITS : frappe un grand coup, monte au créneau, brise le silence, sans appel, change de visage,
  franchit une étape, jette un pavé dans la mare, met le feu aux poudres, fait trembler, coup de tonnerre, séisme
  (au sens figuré), bras de fer (sauf vrai conflit), sur toutes les lèvres, vertement, fustige."""

_SENTENCE_STARTERS = [
    "En outre", "De plus", "Par ailleurs", "Ainsi", "En effet", "Dès lors", "À cet égard", "En somme", "En bref",
    "En conclusion", "Pour conclure", "Force est de constater que", "Il convient de noter que",
    "Il est important de noter que", "Il est important de souligner que", "Il faut noter que", "Notons que",
    "Rappelons que", "Il est à noter que", "En définitive", "D'autre part", "Ceci étant dit", "Cela dit",
]
B = "\\b"   # frontière de mot (écrite ainsi pour éviter toute erreur d'échappement)
_REPLACE = [   # uniquement des remplacements sûrs grammaticalement (le reste passe par la consigne de style)
    (r"\s*[—–]\s*", ", "),
    (r",?\s+en effet\b,?", ""),
    (r",?\s+par ailleurs\b,?", ""),
    (r",?\s+en outre\b,?", ""),
    (B + "joue un rôle (?:clé|crucial|majeur|central|essentiel|déterminant)" + B, "pèse"),
    (B + "jouent un rôle (?:clé|crucial|majeur|central|essentiel|déterminant)" + B, "pèsent"),
    (B + "souligne l'importance de" + B, "insiste sur"),
    (B + "souligne que" + B, "rappelle que"),
    (B + "soulignent que" + B, "rappellent que"),
    (B + "met en lumière" + B, "montre"),
    (B + "mettent en lumière" + B, "montrent"),
    (B + "met en exergue" + B, "montre"),
    (B + "considérablement" + B, "fortement"),
    (B + "significativement" + B, "nettement"),
    (B + "notamment" + B, "en particulier"),
    (B + "néanmoins" + B, "pourtant"),
    (B + "toutefois" + B, "mais"),
    (B + "une véritable" + B, "une"),
    (B + "un véritable" + B, "un"),
    (B + "de véritables" + B, "des"),
    (B + "une nouvelle ère" + B, "une nouvelle étape"),
    (B + "un tournant majeur" + B, "un tournant"),
]


def _keep_case(rep: str):
    def f(m):
        src = m.group(0).lstrip(" ,")
        return rep[:1].upper() + rep[1:] if src[:1].isupper() and rep[:1].isalpha() else rep
    return f


def humanize(text: str) -> str:
    if not text:
        return text
    t = text
    for starter in _SENTENCE_STARTERS:
        # en début de texte, de phrase ou de ligne : on supprime le connecteur et on remet une majuscule
        t = re.sub(r"(^|[.!?]\s+|\n\s*)" + re.escape(starter) + r"\s*,?\s*",
                   lambda m: m.group(1) + "\x00", t, flags=re.IGNORECASE)
    t = re.sub(r"\x00(\w)", lambda m: m.group(1).upper(), t)
    t = t.replace("\x00", "")
    for pat, rep in _REPLACE:
        t = re.sub(pat, _keep_case(rep), t, flags=re.IGNORECASE)
    t = re.sub(r",\s*,", ",", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r" ,", ",", t)
    t = re.sub(r"^\s*,\s*", "", t, flags=re.MULTILINE)
    return t.strip()
