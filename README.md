# Jours de Francis

Site et archives de l'infolettre Jours de Francis.

Chaque nuit, GitHub récupère les campagnes envoyées sur Mailchimp (`scripts/fetch_campaigns.py`), les range brutes dans `raw/`, puis reconstruit le site (`scripts/build_site.py`) et le publie sur GitHub Pages.

## Choisir ce qui apparaît dans les archives

Tout se règle dans `site.json` :

- seules les campagnes envoyées à la liste `liste_archivee` sont publiées ;
- une campagne dont le **nom** dans Mailchimp contient `[hors archive]` est ignorée : c'est le réflexe à prendre pour une annonce ;
- `exclues` liste les anciennes campagnes écartées à la main ; supprimer une ligne la fait réapparaître au prochain passage.

## Publier tout de suite

Onglet Actions → « Synchroniser et publier » → Run workflow. Toute modification poussée sur `main` relance aussi la publication.
