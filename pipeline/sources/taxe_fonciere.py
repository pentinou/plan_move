"""Taux de taxe foncière sur les propriétés bâties (part communale votée),
depuis le REI (Recensement des éléments d'imposition, DGFiP) diffusé par l'OFGL.

Variable E12VOTE = « FB - COMMUNE / TAUX VOTÉ ». Millésimes 2024 et 2025.
Un coût annuel réel pour un propriétaire, qui varie fortement d'une commune à l'autre.
"""

from __future__ import annotations

import httpx

from common import DATA, replace_source

EXPORT_URL = (
    "https://data.ofgl.fr/api/explore/v2.1/catalog/datasets/rei/exports/csv"
    "?select=annee,idcom,valeur&where=var%3D%22E12VOTE%22&delimiter=%3B"
)


def build(con, dept: str | None = None) -> None:
    dest = DATA / "taxe_fonciere" / "taux_fb_communal.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        with httpx.stream("GET", EXPORT_URL, timeout=300, follow_redirects=True) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)
        print(f"  téléchargé {dest.name} ({dest.stat().st_size / 1e6:.1f} Mo)")

    dept_filter = f"AND idcom LIKE '{dept}%'" if dept else ""
    replace_source(con, "taxe_fonciere", f"""
        SELECT idcom AS code_insee,
               TRY_CAST(annee AS SMALLINT) AS annee,
               'taxe_fonciere' AS metric,
               TRY_CAST(valeur AS DOUBLE) AS valeur
        FROM read_csv('{dest}', delim = ';', header = true, all_varchar = true)
        WHERE TRY_CAST(valeur AS DOUBLE) IS NOT NULL
          {dept_filter}
    """)
