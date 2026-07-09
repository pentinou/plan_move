# Plan Move — où déménager, commune par commune

Carte interactive de la France (~35 000 communes) pour choisir où déménager selon des
critères pondérables **en temps réel** : prix immobilier, écoles, sécurité, transports,
dynamisme démographique… Chaque critère affiche son **niveau actuel** et sa
**tendance sur 5 ans** (la commune s'améliore-t-elle ou se dégrade-t-elle ?).

Application 100 % statique : un pipeline Python pré-calcule tout, le navigateur fait le
scoring. Aucun serveur, aucune API externe à l'exécution.

## Prérequis

- **Python ≥ 3.12** et **[uv](https://docs.astral.sh/uv/)** (gestion des dépendances Python)
- **Node.js ≥ 18** et **npm**
- **tippecanoe** (génération des tuiles vectorielles) — voir ci-dessous

Le pipeline cherche tippecanoe dans `pipeline/tools/tippecanoe` (binaire non versionné),
et à défaut dans le `PATH`. Selon votre système :

```bash
# macOS
brew install tippecanoe

# Linux (si le paquet existe)
sudo apt install tippecanoe
# sinon, compiler depuis les sources :
git clone https://github.com/felt/tippecanoe && cd tippecanoe && make -j && sudo make install
```

Une fois installé, il est accessible via le `PATH` : rien de plus à faire. (Sans droits
root, compilez-le et copiez le binaire dans `pipeline/tools/`.)

## Installation & lancement

### En une commande

```bash
# Linux / macOS / WSL
./install.sh                # tout installer + générer les données (long)
./install.sh --dept 44      # variante rapide : un seul département
./install.sh --skip-build   # dépendances seulement, sans générer les données
```

```bat
REM Windows : détecte WSL et y lance install.sh (voir note Windows ci-dessous)
install.bat
```

Puis lancer l'interface : `cd web && npm run dev` → http://localhost:5173

> **Windows** : tippecanoe n'a pas de version Windows native ; l'installation passe par
> **WSL** (Windows Subsystem for Linux). `install.bat` s'en occupe s'il est présent,
> sinon il indique comment l'installer (`wsl --install`).

### Manuellement

```bash
# 1. Générer les données (~2,5 Go de téléchargements mis en cache dans pipeline/data/)
cd pipeline
uv sync                         # crée l'environnement et installe les dépendances
uv run build.py                 # France entière, ~15 min au premier lancement
#   uv run build.py --dept 44           # variante : un seul département (itération rapide)
#   uv run build.py --steps dvf,export  # variante : étapes ciblées

# 2. Lancer l'interface
cd ../web
npm install
npm run dev                     # ouvre http://localhost:5173
```

Le premier lancement télécharge et agrège les open data (long) ; les téléchargements sont
mis en cache dans `pipeline/data/`, les relances sont donc rapides. Pour rafraîchir une
source plus tard : supprimer son fichier dans `pipeline/data/` et relancer l'étape
correspondante suivie de `export` (ex. `uv run build.py --steps dvf,export`).

## Utilisation

- **Sliders** : poids de chaque critère (0 = ignoré) dans le score composite 0-100.
- **↑/↓ mieux** : inverse le sens d'un critère (ex. « prix bas = mieux » par défaut).
- **min/max** : filtres durs sur la valeur brute — les communes hors bornes deviennent grises.
- **Niveau actuel / Tendance 5 ans** : colore la carte par la valeur actuelle ou par
  l'évolution (%/an) de chaque critère.
- **Positif ↑ / négatif ↓** : indique si une valeur élevée améliore ou dégrade le score
  (cliquer pour inverser, info-bulle explicative au survol).
- **Affichage** : cases à cocher pour les noms des communes, les routes principales
  (autoroutes en rouge) et les voies ferrées (pointillés).
- **↺ Réinitialiser les critères** : remet poids, sens et filtres par défaut. Si la carte
  devient toute grise, une bannière explique pourquoi (aucun critère actif, ou un filtre
  min/max qui exclut toutes les communes).
- **Clic sur une commune** : fiche détaillée (valeurs, centiles, évolutions en
  sparklines, écoles avec IPS, top prénoms du département).
- Les réglages sont encodés dans l'URL (partage / favoris).

## Critères et sources (open data, Licence Ouverte)

| Critère | Source | Historique |
|---|---|---|
| Prix des maisons, des terrains à bâtir (€/m² médian), ventes | [DVF géolocalisé](https://files.data.gouv.fr/geo-dvf/) (Etalab/DGFiP) | 5 dernières années (fenêtre glissante) |
| Délinquance (violences, vols, cambriolages… /1000 hab) | [Base communale SSMSI](https://www.data.gouv.fr/datasets/bases-statistiques-communale-departementale-et-regionale-de-la-delinquance-enregistree-par-la-police-et-la-gendarmerie-nationales) | 2016 → |
| Naissances, décès, solde naturel | [INSEE état civil (Melodi)](https://www.data.gouv.fr/datasets/nombre-de-naissances-annuelles-par-commune) | longues séries |
| Écoles à ≤10 km, IPS des écoles | [Annuaire de l'éducation](https://data.education.gouv.fr/explore/dataset/fr-en-annuaire-education/) + [IPS écoles](https://data.education.gouv.fr/explore/dataset/fr-en-ips-ecoles-ap2022/) | IPS : 2022 → |
| Réussite au brevet, valeur ajoutée du collège | [IVAC](https://data.education.gouv.fr/explore/dataset/fr-en-indicateurs-valeur-ajoutee-colleges/) | 2022 → |
| Réussite au bac (lycées généraux et technologiques) | [IVAL](https://data.education.gouv.fr/explore/dataset/fr-en-indicateurs-de-resultat-des-lycees-gt_v2/) | 2012 → |
| Distance à un arrêt de transport en commun | [Arrêts de transport en France](https://transport.data.gouv.fr/datasets/arrets-de-transport-en-france) (agrégat GTFS national) | photo actuelle |
| Orientation politique du maire | [Résultats des municipales 2026](https://www.data.gouv.fr/datasets/elections-municipales-2026-resultats-du-premier-tour) (nuances ministère de l'Intérieur) + [RNE](https://www.data.gouv.fr/datasets/repertoire-national-des-elus-1) (nom du maire) | élection 2026 |
| Médecins généralistes, crèches, équipements de loisirs | [BPE INSEE](https://www.insee.fr/fr/statistiques/8217537) (types D265, D502, F1xx/F3xx) | millésime 2024 |
| Distance à l'hôpital, satisfaction des patients | [FINESS géolocalisé](https://www.data.gouv.fr/datasets/finess-extraction-du-fichier-des-etablissements) + [e-Satis HAS](https://www.data.gouv.fr/datasets/indicateurs-de-qualite-et-de-securite-des-soins-recueil-2025) (hospitalisation +48h MCO) | recueils 2022-2025 |
| Logements sociaux (% des résidences principales) | [RPLS via Caisse des Dépôts](https://opendata.caissedesdepots.fr/explore/dataset/logements-sociaux-dans-les-communes/) | 01/01/2024 |
| Top 10 des prénoms | [Fichier des prénoms INSEE](https://www.insee.fr/fr/statistiques/8595130) | départemental |
| Contours communaux, population | [Contours Etalab/IGN](https://www.data.gouv.fr/datasets/contours-administratifs) + [API Géo](https://geo.api.gouv.fr) | millésime courant |
| Routes principales, voies ferrées (habillage) | [IGN ROUTE 500](https://geoservices.ign.fr/route500) | édition 2021 (dernière) |

## Limites connues des données

- **DVF** ne couvre pas l'Alsace-Moselle (57, 67, 68 — Livre foncier) ni Mayotte,
  et ne publie qu'une fenêtre glissante de 5 ans.
- **« Nombre d'annonces immobilières »** : aucune source ouverte n'existe (Leboncoin,
  SeLoger fermés) — le volume de ventes DVF sert de proxy du dynamisme du marché. Les
  **loyers d'annonce** proviennent de la Carte des loyers de l'ANIL, elle-même construite
  à partir de ~9 M d'annonces Leboncoin/SeLoger via un partenariat officiel (donnée
  d'annonces agrégée légalement, par commune).
- **FiLoSoFi** : revenu et surtout taux de pauvreté sous secret statistique pour les
  petites communes (non diffusés) ; dernier millésime 2021 (le 2022 n'a pas été produit).
- **Qualité des écoles** : pas de taux de réussite en maternelle/primaire ; on utilise
  l'IPS (indice de position sociale) des écoles et les résultats au brevet du collège de
  la commune, sinon du plus proche à vol d'oiseau (la sectorisation n'est pas en open data).
- **SSMSI** : communes à faibles effectifs sous secret statistique — l'estimation fournie
  par le SSMSI est utilisée quand le décompte exact n'est pas diffusé.
- **Prénoms** : granularité départementale (l'INSEE ne publie pas par commune).
- **Orientation politique du maire** : le ministère de l'Intérieur n'attribue de nuance
  qu'aux communes d'environ 3 500 hab et plus (~2 700 communes classables sur l'axe) ;
  ailleurs le critère est « sans donnée » (le nom du maire s'affiche quand même dans la
  fiche). Les nuances « divers » et « régionaliste » ne sont pas classables gauche-droite.
- **Hôpitaux** : aucun « classement » officiel n'existe en open data (le palmarès du Point
  est propriétaire) — la note utilisée est **e-Satis** (satisfaction des patients
  hospitalisés +48h, HAS, /100) de l'établissement MCO noté le plus proche ; distances à
  vol d'oiseau depuis le centre de la commune.
- **Logements sociaux** : taux RPLS (logements sociaux / résidences principales), non
  strictement comparable au taux légal de l'article 55 de la loi SRU (périmètres
  différents) ; à lire comme un ordre de grandeur face à l'objectif de 20-25 %.
- **BPE** (médecins, crèches, loisirs) : millésime 2024 uniquement, pas de tendance.
- Les taux « /1000 hab » utilisent la population légale actuelle, pas celle de chaque année.

## Architecture

Application **100 % statique** : un pipeline Python pré-calcule tout en fichiers plats,
le navigateur charge ces fichiers et fait lui-même le scoring et la coloration.
**Aucun serveur, aucune base de données, aucune API appelée à l'exécution** — une fois les
données générées, l'application tourne hors-ligne et s'héberge n'importe où (GitHub Pages…).

### Flux de données

```
   Open data (data.gouv.fr, INSEE, IGN, éducation.gouv…)
        │   téléchargement + cache (httpx)
        ▼
   pipeline/  ──  Python + uv
        │   DuckDB      : agrégation par commune × année × métrique
        │   tippecanoe  : contours & réseaux → tuiles vectorielles
        ▼
   web/public/data/  ──  fichiers statiques générés
        • communes.pmtiles    tuiles vectorielles des ~35 000 communes
        • metrics.json        niveau + tendance + centiles, par commune
        • series/{dept}.json  séries annuelles (fiche détaillée)
        • reseaux.pmtiles     routes principales + voies ferrées
        ▼
   web/  ──  Vite + TypeScript + MapLibre GL JS
        scoring : score = Σ (poids × centile)  →  recoloration temps réel
        (map.setFeatureState, sans recharger aucune donnée)
```

### Pile technique

| Couche | Outils |
|--------|--------|
| Données | Python 3.12, uv, DuckDB, httpx, scipy, pyproj |
| Cartographie | tippecanoe (tuiles vectorielles), format PMTiles |
| Front | TypeScript, Vite, MapLibre GL JS |
| Échange | JSON + PMTiles statiques (pas de backend) |

### Arborescence

```
pipeline/            Python (uv) — téléchargement, agrégation, export
  build.py           orchestrateur (options --dept, --steps)
  sources/*.py       un module par source → table `metrics` (code_insee × année × métrique)
  export.py          niveau (lissé 3 ans) + tendance (pente 5 ans) + centiles → JSON
  tools/             tippecanoe compilé localement (non versionné)
web/                 Vite + TypeScript + MapLibre GL JS
  public/data/       fichiers générés : *.pmtiles, metrics.json, series/… (non versionnés)
  public/fonts/      glyphes MapLibre auto-hébergés (appli hors-ligne)
  src/
    main.ts          carte, couches, interactions, bannière d'alerte
    scoring.ts       score pondéré (recoloration via setFeatureState)
    panel.ts         panneau de critères (poids, sens, filtres, réinitialisation)
    fiche.ts         fiche commune (sparklines, écoles, prénoms)
    search.ts        recherche de commune par nom
    permalink.ts     réglages encodés dans l'URL (partage / favoris)
```

## Publier sur GitHub

Le dépôt ne contient que le **code source** (~200 Ko). Les données générées
(`pipeline/data/`, `web/public/data/`), `node_modules/` et l'outil `tippecanoe`
sont exclus par `.gitignore` : après un clone, on régénère les données avec le
pipeline (voir « Démarrage »).

L'authentification GitHub se fait par **clé SSH** (`~/.ssh/id_ed25519`, la même que
le reste des projets `pentinou`). Le remote est déjà configuré en SSH.

```bash
# 1. créer un dépôt vide « plan_move » sur https://github.com/new (compte pentinou),
#    SANS README ni .gitignore (ils existent déjà ici)
# 2. pousser :
git push -u origin main
```
