# Publication automatique et notifications : pas à pas

**Le montage conseillé, 100 % gratuit : 1 compte Buffer gratuit par média.** L'offre gratuite de Buffer = 3 réseaux, exactement ce qu'il faut pour le X, l'Instagram et le TikTok d'un média. 5 médias = 5 comptes Buffer (+ 1 sixième, facultatif, pour le compte X « Gros Titre »).

| Réseau | Comment | Ce qui est publié |
|---|---|---|
| **X** | Buffer (Buffer paie l'API X, pas toi) | Tweet + image, tout ce qui est vérifié, vite |
| **Instagram** | Buffer (ou l'API Meta en option) | Le carrousel complet + la description avec sources et question |
| **TikTok** | Buffer | Le carrousel en **plein écran 9:16** + une légende courte avec mots-clés |

**Ce qui part tout seul** : uniquement les posts aux faits vérifiés (✅ ou ✏️). Sensibles ⚠️ et enquêtes 🔎 : seulement si tu coches les cases. Un post faux : supprime-le directement sur le réseau.

## A. Notifications sur ton téléphone (5 min)
1. Installe l'appli **ntfy** (Play Store ou App Store).
2. Touche **+** et colle le sujet affiché dans **Réglages → 📲 Notifications** (serveur ntfy.sh).
3. Dans le studio, clique sur **Envoyer un test**.

Tu es prévenu quand des posts sont prêts, quand c'est publié (compte + réseau) et en cas d'échec.

## B. Les comptes Buffer (10 min par média)
Pour **chaque média** :
1. Crée ses comptes sur les réseaux (voir le dossier `COMPTES` : photo de profil, bio). Passe l'Instagram en **compte professionnel** (Paramètres → Type de compte et outils → Passer à un compte professionnel → Créateur, catégorie « Média/actualités »).
2. Sur **buffer.com**, crée un compte gratuit (une adresse e-mail par compte Buffer ; avec Gmail, l'astuce du `+` marche, par exemple `toi+ballottage@gmail.com`).
3. Dans Buffer, connecte les 3 réseaux du média : **X**, **Instagram**, **TikTok**.
4. Dans Buffer : **Settings → API**, crée une clé et copie-la.
5. Dans le studio : **Réglages → 🚀 Publication automatique → 1. Tes comptes Buffer**, colle la clé dans « Compte Buffer 1 » (2 pour le média suivant, etc.).

Quand les 5 clés sont collées :
6. Clique sur **Charger mes comptes Buffer**.
7. Dans **2. Quel compte pour quel média**, choisis pour chaque média son compte X, Instagram et TikTok.
8. Dans **3. Activer**, coche **publication auto** pour chaque média, puis **Enregistrer** en bas de la page.

**Images** : Buffer récupère les images par une adresse publique. Avec GitHub (voir `GUIDE_GITHUB.md`), c'est automatique. Sur ton PC, coche **Adresse publique automatique (tunnel Cloudflare)** après avoir choisi un mot de passe et installé le tunnel une fois :
```powershell
winget install --id Cloudflare.cloudflared
```

**Limites de Buffer gratuit** : 10 posts programmés en attente par réseau. Le studio envoie chaque post au moment de le publier (90 secondes avant), donc la file ne se remplit jamais : pas de limite par jour côté Buffer. La seule limite est celle de X (50 posts par jour pour un compte non abonné), au-dessus du rythme du studio. Je n'ai pas trouvé de règle de Buffer sur le nombre de comptes gratuits par personne.

## C. Le compte X généraliste « Gros Titre » (facultatif, conseillé)
L'identité est prête dans `COMPTES/Gros Titre` : photo de profil, bannière, bio, tweet à épingler et fiche « à faire ». @grostitre était libre sur X le 25/11/2026.

Un 6e compte X, généraliste, qui publie en continu **le meilleur des 5 médias** (importance 8/10 et plus, ou sujet très chaud), comme les grands comptes d'alertes, qui sont ceux qui grossissent le plus vite sur X.
1. Crée le compte X, connecte-le dans un **6e compte Buffer**, et colle sa clé dans « Compte Buffer 6 ».
2. **Charger mes comptes Buffer**, puis dans « ⭐ Compte X généraliste » : coche **activer**, choisis son compte X, **Enregistrer**.

## D. Le rythme de publication (réglable dans Réglages)
| Réseau | Par défaut | Pourquoi |
|---|---|---|
| X (chaque média) | 20 posts/jour max, 15 min d'écart, info de moins de 3 h | X récompense la vitesse et le volume. Un sujet très chaud passe devant (5 min d'écart) |
| Instagram | 5/jour max, 2 h d'écart, seulement les sujets notés 6/10 et plus | Trop de posts fait baisser la portée de chacun |
| TikTok | 4/jour max, 2 h 30 d'écart, sujets 6/10 et plus | Pareil, et les plus forts d'abord |
| « Gros Titre » | 30/jour max, 12 min d'écart, sujets 8/10 et plus | Le fil des grosses infos |

Chaque soir à partir de 19 h, **« L'essentiel du jour »** (le récap des infos du jour, au même design que les posts) est publié sur Instagram, TikTok et X.

## E. Options avancées
- **Instagram par l'API officielle de Meta** (gratuite, sans Buffer) : crée une app sur developers.facebook.com (cas d'usage « Gérer les messages et le contenu sur Instagram »), puis **Instagram → Configuration de l'API avec connexion Instagram → Générer des jetons d'accès**. Colle l'ID du compte et le jeton dans **Options avancées** de la carte du média.
- **X par l'API officielle** (payante, environ 0,015 $ par tweet) : seulement si tu ne veux pas de Buffer pour X. Réglages → « Option payante : API officielle X ».

*Pourquoi pas un robot qui poste sur x.com à ta place ?* Les règles de X l'interdisent explicitement (« scripter le site X »), avec un risque de **suspension définitive** des comptes. Je ne l'ai donc pas mis.

## F. Tout faire tourner sans ton PC
Une fois les comptes branchés, double-clique sur **`METTRE_EN_LIGNE.bat`** (voir `GUIDE_GITHUB.md`). Il copie tes réglages et tes clés dans GitHub et coupe la publication sur le PC pour éviter les doublons.
