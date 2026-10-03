"""Pipeline Plan Move : télécharge les open data, agrège par commune, exporte pour le web.

Usage :
    uv run build.py                    # tout, France entière
    uv run build.py --dept 44          # limite les données au département 44 (itération rapide)
    uv run build.py --steps dvf,export # étapes ciblées
    uv run build.py --refresh          # revalide les fichiers en cache, retélécharge ceux qui ont changé
"""

from __future__ import annotations

import argparse
import datetime
import importlib
import json
import time

import common

STEPS = ["geometries", "dvf", "ssmsi", "etat_civil", "ecoles", "loyers", "filosofi",
         "taxe_fonciere", "transports", "prenoms", "reseaux", "maires", "bpe",
         "hopitaux", "logement_social", "export"]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dept", help="code département pour limiter les données (ex: 44)")
    p.add_argument("--steps", default="all", help=f"étapes, parmi : {','.join(STEPS)}")
    p.add_argument("--refresh", action="store_true",
                   help="revalider chaque fichier en cache auprès de sa source et retélécharger ceux qui ont changé")
    args = p.parse_args()
    common.REFRESH = args.refresh

    steps = STEPS if args.steps == "all" else args.steps.split(",")
    unknown = set(steps) - set(STEPS)
    if unknown:
        p.error(f"étapes inconnues : {unknown}")

    con = common.connect()
    for i, step in enumerate(steps, 1):
        module = importlib.import_module("export" if step == "export" else f"sources.{step}")
        print(f"» [{i}/{len(steps)}] {step}")
        t0 = time.time()
        module.build(con, args.dept)
        print(f"  ({time.time() - t0:.0f}s)")
    con.close()
    if args.refresh:
        print(f"» {len(common.CHANGED)} fichier(s) source (re)téléchargé(s)"
              + (" : " + ", ".join(common.CHANGED) if common.CHANGED else ""))
        (common.DATA / "refresh.json").write_text(json.dumps(
            {"date": datetime.datetime.now().isoformat(timespec="seconds"), "changed": common.CHANGED},
            indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
