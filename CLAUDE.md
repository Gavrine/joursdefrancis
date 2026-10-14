# Jours de Francis — notes de travail

Fichier de contexte pour reprendre le projet dans une nouvelle conversation sans tout réexpliquer.

## L'auteur et le projet

- Infolettre littéraire « Jours de Francis », journal intime et littéraire, envoyée via Mailchimp (audience « Jours de Francis », compte us3). Environ 870 inscrits, ~300 ouvertures.
- L'auteur publie sous le nom de Francis ; le volume 1, *Passer janvier*, est paru aux éditions du Nénufar (lenenufar.fr).
- Chaîne YouTube : Infra-ordinaire (@infra.ordinaire), courts métrages expérimentaux. Compte Instagram : joursdefrancis.
- Il est aussi photographe professionnel : activité sans aucun rapport, ne jamais mélanger les deux.
- Ton attendu : français, direct, sans flatterie, pas de questions en fin de réponse.

## Le site

- En ligne sur https://joursdefrancis.fr (hébergement Infomaniak, dossier `/sites/joursdefrancis-statique`). L'ancien WordPress est intact dans `/sites/joursdefrancis.fr` : remettre ce dossier racine dans Infomaniak suffit pour revenir en arrière.
- Copie de prévisualisation : https://gavrine.github.io/joursdefrancis/ (branche `gh-pages`).
- Les DNS n'ont pas été modifiés (messagerie Infomaniak et authentification Mailchimp intactes).

## Fonctionnement

- `.github/workflows/sync.yml` tourne chaque nuit (~6 h, heure de Paris), à chaque push sur `main`, ou à la main (Actions → « Synchroniser et publier » → Run workflow).
- Étapes : `scripts/fetch_campaigns.py` récupère les campagnes envoyées via l'API Mailchimp dans `raw/` → `scripts/build_site.py` nettoie et génère le site → publication sur `gh-pages` → seconde construction à la racine (`JDF_BASE=""`, `JDF_CIBLE=infomaniak`) envoyée en FTP chiffré (lftp) vers Infomaniak.
- Secrets GitHub : `MAILCHIMP_API_KEY`, `INFOMANIAK_HOST` (kq4mzd.ftp.infomaniak.com), `INFOMANIAK_USER` (kq4mzd_envoi, utilisateur FTP limité au dossier du site), `INFOMANIAK_PASSWORD`.
- Les erreurs des scripts s'affichent en annotations GitHub (`::error::`) ; elles se lisent via l'API `check-runs/{job}/annotations`, les journaux bruts n'étant pas accessibles depuis l'environnement de Claude.

## Où se règle quoi

- `site.json` : textes de l'accueil (accroche, présentation, bloc livre, bloc vidéo), formulaire Mailchimp, campagnes `exclues`, `retouches` (paragraphes à retirer d'un texte, repérés par leurs premiers mots).
- Règles de sélection : seules les campagnes de la liste « Jours de Francis » ; une campagne dont le **nom** Mailchimp contient `[hors archive]` est ignorée.
- `scripts/build_site.py` : nettoyage (pieds de page Mailchimp, liens de navigation, formules « Cher abonné » en tête, titres répétés), titres (« Jours de Francis N : » retiré, emojis retirés, majuscule initiale), pages accueil / archives / textes, flux RSS.
- `assets/style.css` : apparence (EB Garamond, papier #f6f1e7, vermillon de la couverture).

## Décisions prises avec l'auteur

- Archives : liste continue des titres avec extrait, sans dates ni années. 74 textes à partir d'avril 2018 ; les trois premiers envois (2016-2017), la liste frog.lu, les annonces et messages de service sont exclus.
- Accueil : texte de présentation rédigé par l'auteur, à reprendre mot pour mot ; pas de blagues sur Francis ; pas de mention de lieu de résidence.
- Instagram : un post par envoi (visuel sobre), story avec lien vers la page du texte ; carrousels parodiant les codes du développement personnel avec des phrases tirées des textes, dernière image vermillon renvoyant au site. Ne pas parodier des comptes de femmes.

## En suspens

- Tester le formulaire d'inscription du site avec une adresse secondaire (vérifier l'audience de destination).
- Modifier les mails/pages de confirmation dans Mailchimp (menu Formulaires).
- Pistes de croissance : échanges de recommandations avec d'autres infolettres, présence Substack/Kessel, encart dans le livre, plan du site + Search Console, lien « Envoyer ce texte à quelqu'un », génération automatique des visuels Instagram.
- Résilier le WordPress seulement après quelques jours sans problème.
