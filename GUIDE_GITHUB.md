# Mettre le studio en ligne avec GitHub : le guide complet, pas à pas

## D'abord, c'est quoi et pourquoi ?

Aujourd'hui, le studio tourne **sur ton PC** : s'il est éteint ou sans internet, rien ne se passe.

**GitHub** est un site (de Microsoft) où les développeurs rangent leur code. Il offre deux services gratuits qui nous intéressent :
- **GitHub Actions** : des ordinateurs de GitHub qui lancent un programme à heure fixe. Le nôtre lance le studio **toutes les 15 minutes** : il lit l'actu, écrit, vérifie, crée les images et publie.
- **GitHub Pages** : un petit site web gratuit. Le studio y met la **page de tes posts**, consultable sur ton téléphone.

Résultat : **ton PC peut être éteint ou sans connexion**, tout se passe chez GitHub. Pas de carte bancaire, il faut juste une adresse e-mail.

Quelques mots que tu vas croiser :
- **Dépôt** (*repository*, *repo*) : un dossier en ligne qui contient le code du studio.
- **Secret** : une valeur cachée et chiffrée (ta clé Gemini, tes clés Buffer…). Personne ne peut la lire, même pas toi sur le site : seul le robot y a accès.
- **Workflow** : la « recette » du robot (le fichier `.github/workflows/studio.yml`, déjà prêt).

---

## Étape 0 : prépare ton studio sur le PC (une fois)

Le programme de mise en ligne recopie tes réglages, donc remplis-les d'abord :
1. Lance le studio (`LANCER.bat`) et va dans **⚙️ Réglages**.
2. **Clé Gemini** collée et testée (bouton « Tester »).
3. **Notifications ntfy** : l'appli sur ton téléphone, abonnée à ton sujet (bouton « Envoyer un test »).
4. **Publication** : tes clés Buffer collées, « Charger mes comptes Buffer » cliqué, et pour chaque média le compte X, Instagram et TikTok choisis dans le tableau, puis « publication auto » cochée. Voir `PUBLICATION_AUTO.md`.
5. Clique sur **Enregistrer** en bas.

---

## Méthode facile : un double-clic (conseillé)

### 1. Crée ton compte GitHub (3 min)
1. Va sur **github.com** et clique sur **Sign up**.
2. Mets ton e-mail, un mot de passe, un nom d'utilisateur (il apparaîtra dans l'adresse de ta page, par exemple `tonpseudo.github.io`).
3. Valide le code reçu par e-mail. Choisis l'offre **Free** si on te le demande. Pas de carte bancaire.

### 2. Double-clique sur `METTRE_EN_LIGNE.bat`
Il est dans le dossier `media-auto`. Une fenêtre noire s'ouvre. Voici ce qui se passe, dans l'ordre :

1. **Installation de Git et de GitHub CLI** (seulement la 1re fois) : ce sont les outils officiels pour parler à GitHub. Windows peut te demander d'accepter les conditions de winget (tape `Y` puis Entrée) et d'autoriser l'installation (clique sur **Oui**).
   - Si la fenêtre dit qu'un outil n'est pas trouvé juste après l'installation : **ferme-la et double-clique à nouveau** sur `METTRE_EN_LIGNE.bat` (Windows doit « voir » les nouveaux programmes).
2. **Connexion à GitHub** : la fenêtre affiche un code à 8 caractères (par exemple `ABCD-1234`) et ouvre ton navigateur.
   - Si on te demande « Authenticate Git with your GitHub credentials? », réponds **Y**.
   - Dans le navigateur : connecte-toi à GitHub, colle le code, clique sur **Continue**, puis **Authorize github**.
   - Reviens à la fenêtre noire : elle affiche « ✅ Connecté à GitHub : tonpseudo ».
3. **Nom du dépôt** : appuie simplement sur **Entrée** pour garder `studio-medias`.
4. **« Le dépôt sera PUBLIC… On continue ? »** : appuie sur **Entrée** (= oui). Public est obligatoire pour la gratuité illimitée. Le code se voit, **jamais tes clés**.
5. Le programme travaille tout seul (1 à 2 min) :
   - 📦 création du dépôt et ⬆️ envoi du code (sans ton dossier `data/`, donc sans clés) ;
   - 🔐 copie de tes clés dans les secrets chiffrés ;
   - 🌐 activation de la page des posts ;
   - 🤖 activation du robot et lancement du premier passage.
6. **« Couper la publication auto sur ce PC ? »** : appuie sur **Entrée** (= oui). Sinon, ton PC et GitHub publieraient les mêmes posts en double.
7. À la fin, la fenêtre affiche **🎉 C'EST EN LIGNE** et deux adresses : garde-les.

### 3. Vérifie que ça marche (10 min après)
1. Ouvre l'adresse **Suivi du robot** (`https://github.com/tonpseudo/studio-medias/actions`).
2. Tu vois une ligne « studio-medias » :
   - 🟡 rond jaune qui tourne : en cours (5 à 10 min la 1re fois) ;
   - ✅ coche verte : tout va bien ;
   - ❌ croix rouge : voir « Problèmes fréquents » plus bas.
3. Ouvre l'adresse **Page des posts** (`https://tonpseudo.github.io/studio-medias/`) : tu vois les posts de chaque média. Ajoute-la à l'écran d'accueil de ton téléphone.
4. Ensuite, le robot repasse **tout seul toutes les 15 minutes**, jour et nuit. Tu reçois les notifications ntfy comme avant.

C'est fini. Tu peux éteindre ton PC.

---

## Au quotidien

| Je veux… | Je fais… |
|---|---|
| Voir les posts | La page des posts (mise à jour toutes les 15 min) |
| Savoir ce qui est publié | Les notifications ntfy sur ton téléphone |
| Retirer un post faux | Supprime-le directement sur X, Instagram ou TikTok |
| Changer un réglage (clé, compte Buffer, rythme…) | Change-le dans le studio sur ton PC, **Enregistrer**, puis double-clique à nouveau sur `METTRE_EN_LIGNE.bat` |
| Mettre à jour le studio (nouvelle version) | Double-clique sur `METTRE_EN_LIGNE.bat` : il renvoie le nouveau code |
| Mettre la publication en pause | Sur GitHub : ton dépôt → **Settings** → **Secrets and variables** → **Actions** → onglet **Variables** → **New repository variable** : nom `AUTO_PUBLISH`, valeur `0`. Pour reprendre : mets `1` |
| Tout arrêter | Ton dépôt → onglet **Actions** → « studio-medias » à gauche → bouton **…** → **Disable workflow** (et **Enable** pour relancer) |
| Lancer un passage tout de suite | Onglet **Actions** → « studio-medias » → **Run workflow** → **Run workflow** |

**Autres options** (même endroit que `AUTO_PUBLISH`, onglet **Variables**) :
- `AUTO_SENSITIVE` = `1` : publier aussi seuls les sujets sensibles vérifiés (à tes risques) ;
- `AUTO_ENQUETES` = `1` : publier aussi seules les enquêtes.

---

## Problèmes fréquents

| Ce que tu vois | Pourquoi | Solution |
|---|---|---|
| ❌ croix rouge dans Actions | Une étape a échoué | Clique sur la ligne rouge, puis sur « passage » : l'étape en rouge dit pourquoi. Les causes les plus courantes sont ci-dessous |
| « Aucune clé Gemini » dans le journal | Le secret `GEMINI_API_KEY` manque | Mets la clé dans le studio (Réglages), Enregistrer, relance `METTRE_EN_LIGNE.bat` |
| « quota atteint » / « Gemini saturé » | Quota gratuit de Gemini épuisé pour la journée | Rien à faire : le robot reprend tout seul. Pour ne jamais bloquer : active la facturation Gemini (quelques euros/mois) |
| « Clé Buffer refusée » (notification ⚠️) | Clé Buffer supprimée ou recopiée de travers | Recrée une clé dans Buffer (Settings → API), colle-la dans le studio, Enregistrer, relance `METTRE_EN_LIGNE.bat` |
| La page des posts affiche « 404 » | Le tout premier passage n'est pas fini | Attends la coche verte (10 min) |
| Rien ne se passe depuis des heures | GitHub a désactivé le robot (rare) | Onglet **Actions** → « studio-medias » → **Enable workflow** |
| La fenêtre noire dit « gh n'est pas installé » | Windows ne voit pas encore le nouvel outil | Ferme la fenêtre et double-clique de nouveau sur `METTRE_EN_LIGNE.bat` |
| « refusing to allow an OAuth App to create or update workflow » | Il manque une autorisation | Relance `METTRE_EN_LIGNE.bat` et valide la page qui s'ouvre (« workflow ») |

---

## Bon à savoir (honnêtement)

- **Gratuit et sans carte** : un dépôt public a des minutes GitHub Actions illimitées.
- **Zone grise** : GitHub Actions est prévu pour les projets de code. Un robot toutes les 15 min est toléré dans les faits, mais GitHub pourrait le désactiver. Dans ce cas, relance simplement le studio sur ton PC (`LANCER.bat`) : rien n'est perdu.
- **Horaires approximatifs** : aux heures de pointe, GitHub décale parfois un passage de 5 à 30 min.
- **La page des posts est publique** mais non référencée sur Google (garde l'adresse pour toi). Elle ne montre que ce qui est de toute façon publié sur tes comptes.
- **Tes clés ne sont jamais écrites dans le code ni sur le disque des serveurs** : elles restent dans les secrets chiffrés et sont relues à chaque passage.
- **Pause de 60 jours** : GitHub met en pause les robots des dépôts inactifs depuis 60 jours. Le studio fait tout seul une petite mise à jour tous les 50 jours pour l'éviter.

---

## Méthode manuelle (si tu préfères tout faire sur le site)

1. Dans `media-auto`, lance `python preparer_github.py` : il crée le dossier `POUR_GITHUB` (sans clés).
2. Sur github.com : **+** (en haut à droite) → **New repository** → nom `studio-medias` → **Public** → **Create repository**.
3. Clique sur **uploading an existing file**, glisse **tout le contenu** de `POUR_GITHUB` (y compris le dossier `.github`), puis **Commit changes**.
4. **Settings** → **Secrets and variables** → **Actions** → **New repository secret**, pour chaque ligne affichée par `python secrets_pour_github.py` (nom + valeur).
5. **Settings** → **Pages** → *Build and deployment* → *Source* : **GitHub Actions**.
6. Onglet **Actions** → **I understand my workflows, go ahead and enable them** si demandé → « studio-medias » → **Run workflow**.
7. Dans le studio de ton PC, décoche « publication auto » pour chaque média (pas de doublons).
