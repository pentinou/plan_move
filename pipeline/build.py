"""Pipeline Plan Move : télécharge les open data, agrège par commune, exporte pour le web.

Usage :
    uv run build.py                    # tout, France entière
    uv run build.py --dept 44          # limite les données au département 44 (itération rapide)
    uv run build.py --steps dvf,export # étapes ciblées
"""

from __future__ import annotations

import argparse
import importlib
import time

import common

STEPS = ["geometries", "dvf", "ssmsi", "etat_civil", "ecoles", "loyers", "filosofi",
         "taxe_fonciere", "transports", "prenoms", "reseaux", "maires", "bpe",
         "hopitaux", "logement_social", "export"]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dept", help="code département pour limiter les données (ex: 44)")
    p.add_argument("--steps", default="all", help=f"étapes, parmi : {','.join(STEPS)}")
    args = p.parse_args()

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


if __name__ == "__main__":
    main()
