# Studio Médias

Un site-outil qui prépare **tout seul**, pour 5 médias de niche, des posts prêts à publier :
- **Instagram / TikTok** : un carrousel de 3 images dans le style des comptes d'actu (photo + bandeau « 🚨 DERNIÈRE MINUTE » + phrase-chapeau sur dégradé noir, puis « l'essentiel » en bulles, puis « abonne-toi ») et sa description ;
- **X** : un tweet « 🇫🇷 FLASH - … (via …) » avec une photo (ou deux côte à côte).

Par défaut rien n'est publié à ta place : tu copies, tu télécharges, tu postes, puis tu coches « Posté ».
**Publication automatique gratuite (1 compte Buffer par média : X, Instagram, TikTok) et notifications sur ton téléphone (ntfy)** : voir [PUBLICATION_AUTO.md](PUBLICATION_AUTO.md).
**En ligne 24h/24, PC éteint, gratuit** : double-clique sur `METTRE_EN_LIGNE.bat`, tout est expliqué dans [GUIDE_GITHUB.md](GUIDE_GITHUB.md).
**Formats** : post d'actu (carrousel + tweet), version TikTok plein écran 9:16, « L'essentiel du jour » chaque soir, enquêtes de fond.
**Ce que tu dois faire pour lancer les comptes** : voir [GUIDE_LANCEMENT.md](GUIDE_LANCEMENT.md).

## Lancer le studio
- **Double-clique sur `LANCER.bat`**. La première fois, il installe ce qu'il faut (environ 1 minute), puis le site s'ouvre sur http://localhost:8765.
- Pour ne plus jamais y penser : **⚙️ Réglages → coche « Lancer le studio tout seul au démarrage de Windows »**. Le studio tourne alors en arrière-plan dès que tu allumes ton PC. Ouvre http://localhost:8765 (ou relance `LANCER.bat`) quand tu veux voir les posts.
- Sur ton téléphone (même Wi-Fi) : l'adresse `http://192.168.x.x:8765` s'affiche au lancement.
- Si tu déplaces le dossier, décoche puis recoche le démarrage avec Windows.

## Comment il travaille tout seul
1. Toutes les 10 minutes, il relit les sources de chaque média. C'est gratuit, sans IA.
2. Il regroupe les articles par sujet et ne garde que **l'actu du jour** : au moins un article daté de moins de 12 h.
3. Il ne fait travailler l'IA que si un sujet **chauffe** : repris par au moins 3 médias (2 pour la tech) dans les 3 dernières heures, ou avec un mot fort (démission, record, accord…). Il relance aussi un compte resté 3 h sans post.
4. Gemini choisit les meilleurs sujets pour la niche et rédige tout. Les textes passent ensuite par un **filtre anti-« style IA »** : il retire les tirets cadratins, « en outre », « joue un rôle crucial », etc.
5. **Photo** : d'abord la vraie personne ou le vrai lieu sur Wikipédia, sinon la photo de l'article (marquée 📰, créditée au média), sinon une photo libre d'illustration. Si Wikipédia était saturé, le studio retente plus tard tout seul.
6. La nuit (de 23h à 7h), seules les très grosses infos, reprises par 5 médias ou plus, déclenchent un post.

Tout se règle dans **⚙️ Réglages** : clé Gemini, fréquence, seuil de « sujet chaud », heures, nombre de posts, format, noms et couleurs.

## Vérification des faits (anti-désinformation)
Avant d'enregistrer un post, le studio :
1. lit le **texte complet** de 2 à 4 articles de médias différents, pas seulement le résumé RSS. Pour les sites qui refusent les robots (Le Monde, L'Équipe, Libération, France 24…), il ouvre la page dans un **vrai navigateur Chrome**, comme un lecteur. La fenêtre est placée hors de l'écran et peut apparaître brièvement dans la barre des tâches. Il lit seulement ce qu'un visiteur non abonné voit (aucun contournement de paywall) et passe à un autre média si un test anti-robot s'affiche. Le texte sert uniquement à vérifier, il n'est jamais republié ;
2. fait contrôler **chaque affirmation** (noms, chiffres, dates, citations) par une seconde passe d'IA « vérificateur » ; ce qui n'est pas confirmé est corrigé ou retiré ;
3. vérifie que **la photo Wikipédia est la bonne personne** (sinon il en prend une autre) ;
4. **écarte** le sujet si le fait principal n'est confirmé nulle part, ou si c'est un sujet sensible impossible à vérifier.

Badges : ✅ faits vérifiés · ✏️ corrigé (survole le badge pour voir les corrections) · ⚠️ non vérifié (relis bien).
Ça réduit fortement le risque d'erreur, mais ça ne le supprime pas : l'IA peut encore se tromper, relis avant de publier.

**Gemini gratuit sature parfois en fin de journée** : le studio s'arrête alors tout de suite et réessaie 10 minutes plus tard. Pour plus de fiabilité, active la facturation sur ta clé Gemini (aistudio.google.com) : avec les modèles Flash-Lite, compte environ 5 à 10 € par mois pour tes 5 médias (estimation, selon le nombre de posts).

## Enquêtes automatiques 🔎
Tous les 3 jours (à partir de 18h), chaque média produit **L'ENQUÊTE** : un dossier de fond sur l'affaire la plus suivie de sa niche cette semaine. Il comprend un carrousel de 6 à 7 images (chronologie, chiffres clés, acteurs, ce qui fait débat, ce qu'on ne sait pas encore), une longue description et un **fil X**, le tout vérifié.
C'est une enquête documentaire (synthèse vérifiée de plusieurs médias), pas une enquête de terrain : pas d'interview ni de document exclusif.
Bouton « 🔎 Lancer une enquête » sur chaque média, et fréquence réglable dans Réglages.

## Tes comptes
Le dossier **COMPTES** (à côté du studio) contient, pour chaque média, la photo de profil, la bannière X, les bios (TikTok, Instagram, X) et une fiche **A_FAIRE.md**. Pour les régénérer après un changement de nom ou de couleur :
```powershell
python generer_comptes.py
```

## Les 5 médias
| Média | Niche | Exemples de sources |
|---|---|---|
| **ballottage** | Politique française | franceinfo, Le Monde, Le Figaro, BFMTV, 20 Minutes, Libération, Google News |
| **la fraîche** | Argent et éco du quotidien | franceinfo, Le Monde, Le Figaro, BFM Business, La Tribune, Google News |
| **ctrl** | Tech et IA | Le Monde Pixels, Numerama, Frandroid, 01net, Les Numériques, Clubic… |
| **petit pont** | Sport (foot d'abord) | L'Équipe, RMC Sport, franceinfo, Foot Mercato, Google News |
| **fuseau horaire** | Monde et géopolitique | franceinfo, France 24, RFI, Courrier international, Google News |

Ligne éditoriale et sources : `medias.yaml` (pour les utilisateurs avancés).

## Coût : 0 €
- IA : Gemini, palier gratuit. L'IA n'est appelée que pour les sujets chauds, environ 30 à 80 fois par jour pour les 5 médias.
- Sources : flux RSS publics. Photos : Wikipédia, Openverse, Pexels (clé gratuite et optionnelle), ou celle de l'article.
- Police Poppins (licence libre OFL), emojis 3D Microsoft Fluent (licence MIT), téléchargés une fois.

## Sur chaque post
- Badges :
  - **🔥 Sujet chaud** : à poster en priorité.
  - **⚠️ Sujet sensible** : à relire avec attention.
  - **📰 Photo de l'article** : les droits appartiennent au média ou à l'agence, ce qui comporte un risque de réclamation. Décoche l'option dans Réglages pour l'éviter.
- Les textes sont modifiables dans le site avant de les copier.
- **🔄 Refaire les visuels** : retente la recherche de photo.

Tu restes responsable de ce que tu publies : relis toujours avant de poster.
