# Héberger le studio gratuitement, 24h/24, sans carte bancaire

*Recherches du 24/11/2026. Les offres gratuites changent souvent.*

## La solution retenue : GitHub (gratuit, sans carte, PC éteint)

👉 **Le pas-à-pas complet est dans [GUIDE_GITHUB.md](GUIDE_GITHUB.md).** En résumé : tu crées un compte sur github.com, puis tu double-cliques sur **`METTRE_EN_LIGNE.bat`**. Il fait tout le reste : dépôt, envoi du code, copie de tes clés dans les secrets chiffrés, page des posts, robot.

Ensuite, toutes les 15 minutes, les serveurs de GitHub lancent le studio : actu, vérification, visuels, enquêtes, récap du soir, publication. **Ton PC peut être éteint ou sans connexion.**

## Pourquoi pas ailleurs ?

| Option | Prix | Carte bancaire | 24h/24 | Verdict |
|---|---|---|---|---|
| **GitHub Actions + GitHub Pages** | 0 € | ❌ Non | ✅ Passage toutes les 15 min | **Retenu** |
| Ton PC (LANCER.bat) | 0 € | ❌ Non | Seulement PC allumé | Plan B, et pour régler le studio |
| Oracle Cloud, Google Cloud | 0 € | ⚠️ Oui (vérification) | ✅ | Écarté, carte exigée |
| Render, Koyeb, Railway, Hugging Face… | 0 € | Selon l'offre | ❌ Mise en veille, ou carte | Écarté |

## Limites (honnêtement)
- **Zone grise des conditions de GitHub** : Actions est prévu pour les projets logiciels. Toléré dans les faits, mais GitHub peut désactiver le robot. Plan B : `LANCER.bat` sur ton PC.
- **Horaires approximatifs** : un passage peut être décalé de 5 à 30 min aux heures de pointe.
- **Page en ligne en lecture seule** : un post faux se supprime directement sur le réseau. Les réglages se changent dans le studio du PC, puis on relance `METTRE_EN_LIGNE.bat`.
- **Une seule machine qui publie** : le programme de mise en ligne propose de couper la publication sur le PC (pas de doublons).
- **Gemini gratuit** : avec 5 médias, le quota peut être atteint le soir. Le studio reprend le lendemain. Pour ne jamais bloquer : facturation Gemini (quelques euros par mois).

## Comment ça marche (pour info)
- `.github/workflows/studio.yml` lance `run_cloud.py` toutes les 15 min.
- La mémoire du studio (posts, cache) est gardée d'un passage à l'autre dans le cache de GitHub, **sans aucune clé** : elles sont relues dans les secrets à chaque passage. Les jetons Instagram prolongés sont chiffrés.
- Les images sont mises en ligne sur GitHub Pages, puis Buffer ou Instagram les récupèrent au passage suivant (15 min plus tard).
- GitHub coupe les robots des dépôts inactifs depuis 60 jours : le workflow fait tout seul un « commit vide » tous les 50 jours.
