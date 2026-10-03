# Paquet YunoHost de Plan Move (branche `yunohost`)

Deux branches :

- **`main`** : le programme, utilisable par tous (pipeline + carte), sans rien de propre
  à un serveur.
- **`yunohost`** : `main` + ce dossier `ynh/` (paquet YunoHost) et les réglages du
  serveur. On y fusionne `main` régulièrement : `git checkout yunohost && git merge main`.
  Toute amélioration générale se fait d'abord sur `main`.

## Ce que fait l'application

- Le site (100 % statique) est servi par nginx depuis `$data_dir/site`.
- Le 1er de chaque mois à 3 h (`planmove-update.timer`), `ynh/conf/update.sh` :
  `build.py --refresh` (ne retélécharge que les sources qui ont changé), `check.py`
  (compare à la version en ligne), `npm run build`, puis publie — ou garde la version en
  ligne si une étape échoue. Compte rendu par mail (`report_email`).
- Lancer une mise à jour à la main : `sudo systemctl start planmove-update`
  (journal : `/var/log/planmove/update.log` et `$data_dir/derniere-maj.log`).

Installation : `sudo yunohost app install ./ynh -a "domain=plan.example.org&path=/&init_main_permission=visitors&report_email=moi@example.org"`

Particularité du serveur d'origine (Core 2, sans SSE4.2) : `numpy<2.3` imposé dans
`scripts/_common.sh`.
