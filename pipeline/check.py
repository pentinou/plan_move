"""Contrôle des données exportées pour le web, avant de les publier.

    uv run check.py                                   # contrôle web/public/data
    uv run check.py --previous ../site/data/metrics.json   # + compare à la version en ligne
    uv run check.py --json rapport.json               # écrit aussi le résultat en JSON

Code de sortie 1 si une ERREUR est trouvée (les AVERTISSEMENTS ne bloquent pas) : un
script de mise à jour peut alors garder la version en ligne au lieu de publier.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

import export
from common import WEB_DATA
from sources import dvf

MIN_COMMUNES = 34_000      # ~34 900 communes en France
MAX_BAISSE = 0.20          # couverture d'un critère : baisse tolérée vs la version en ligne


def couvertures(metrics: dict) -> dict[str, float]:
    """Part des communes ayant une valeur, pour chaque critère."""
    ids = [m["id"] for m in metrics["metrics"]]
    n = len(metrics["communes"]) or 1
    return {mid: sum(c["v"][i] is not None for c in metrics["communes"].values()) / n
            for i, mid in enumerate(ids)}


def controler(data: Path, previous: Path | None) -> tuple[list[str], list[str], list[str]]:
    erreurs, avertissements, infos = [], [], []
    try:
        m = json.loads((data / "metrics.json").read_text())
    except (OSError, ValueError) as e:
        return [f"metrics.json illisible : {e}"], [], []

    infos.append(f"généré le {m.get('generated')}, {len(m['communes'])} communes, {len(m['metrics'])} critères")
    if len(m["communes"]) < MIN_COMMUNES:
        erreurs.append(f"{len(m['communes'])} communes seulement (attendu ≥ {MIN_COMMUNES})")
    attendus = [x["id"] for x in export.METRICS]
    if [x["id"] for x in m["metrics"]] != attendus:
        erreurs.append("la liste des critères ne correspond pas au registre export.METRICS")

    cov = couvertures(m)
    for mid, c in cov.items():
        if c == 0:
            erreurs.append(f"critère « {mid} » vide pour toutes les communes")

    if previous and previous.exists():
        try:
            old = json.loads(previous.read_text())
        except ValueError:
            old = None
        if old:
            if len(m["communes"]) < 0.99 * len(old["communes"]):
                erreurs.append(f"communes : {len(old['communes'])} → {len(m['communes'])}")
            old_cov = couvertures(old) if [x["id"] for x in old["metrics"]] == list(cov) else {}
            for mid, c in cov.items():
                if mid in old_cov and c < (1 - MAX_BAISSE) * old_cov[mid]:
                    erreurs.append(f"critère « {mid} » : couverture {old_cov[mid]:.0%} → {c:.0%}")

    for nom in ("communes.pmtiles", "reseaux.pmtiles"):
        f = data / nom
        if not f.exists() or f.read_bytes()[:7] != b"PMTiles":
            erreurs.append(f"{nom} absent ou invalide")
    try:
        deps = json.loads((data / "departements.geojson").read_text())
        if len(deps.get("features", [])) < 96:
            erreurs.append(f"departements.geojson : {len(deps.get('features', []))} départements")
    except (OSError, ValueError) as e:
        erreurs.append(f"departements.geojson illisible : {e}")
    n_series = len(list((data / "series").glob("*.json")))
    if n_series < 90:
        erreurs.append(f"series/ : {n_series} départements seulement")

    # Les millésimes sont listés dans le code : une nouvelle année publiée demande une
    # modification (on la signale, sans bloquer).
    suivante = max(dvf.YEARS) + 1
    try:
        with httpx.stream("GET", f"{dvf.BASE}/{suivante}/full.csv.gz", follow_redirects=True, timeout=60) as r:
            if r.status_code == 200:
                avertissements.append(f"DVF {suivante} est publié : l'ajouter à YEARS dans sources/dvf.py")
    except httpx.HTTPError:
        pass
    return erreurs, avertissements, infos


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", type=Path, default=WEB_DATA, help="dossier à contrôler (défaut : web/public/data)")
    p.add_argument("--previous", type=Path, help="metrics.json de la version en ligne, pour comparer")
    p.add_argument("--json", type=Path, help="écrire le résultat dans ce fichier")
    a = p.parse_args()

    erreurs, avertissements, infos = controler(a.data, a.previous)
    for x in infos:
        print(f"  {x}")
    for x in avertissements:
        print(f"  AVERTISSEMENT : {x}")
    for x in erreurs:
        print(f"  ERREUR : {x}")
    print("  contrôle : " + ("ÉCHEC" if erreurs else "OK"))
    if a.json:
        a.json.write_text(json.dumps({"ok": not erreurs, "erreurs": erreurs, "avertissements": avertissements,
                                      "infos": infos}, indent=1, ensure_ascii=False))
    sys.exit(1 if erreurs else 0)


if __name__ == "__main__":
    main()
