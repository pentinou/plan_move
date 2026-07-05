"""Carte des loyers (ANIL / Ministère du Logement) → loyer d'annonce €/m²
charges comprises, par commune, pour maisons et appartements.

Estimé à partir de ~9 M d'annonces Leboncoin/SeLoger via un partenariat officiel :
c'est la donnée « prix des annonces » obtenue légalement et agrégée.
Millésimes retenus pour la tendance : 2022 à 2025 (le format 2018-2021 diffère).
"""

from __future__ import annotations

from pathlib import Path

from common import DATA, datagouv_resources, download, remap_plm, replace_source

YEARS = [2022, 2023, 2024, 2025]


def _to_utf8(path: Path) -> Path:
    """Réécrit le CSV en UTF-8 s'il est en latin-1 (idempotent, mis en cache)."""
    with open(path, "rb") as f:
        head = f.read(4096)
    try:
        head.decode("utf-8")
        return path
    except UnicodeDecodeError:
        pass
    out = path.with_suffix(".utf8.csv")
    if not out.exists():
        out.write_text(path.read_bytes().decode("latin-1"), encoding="utf-8")
    return out


def _resolve(year: int, kind: str) -> str:
    """kind = 'mai' (maison) ou 'app' (appartement toutes tailles)."""
    resources = datagouv_resources(f"carte-des-loyers-indicateurs-de-loyers-dannonce-par-commune-en-{year}")
    for r in resources:
        if r["format"] != "csv":
            continue
        title = r["title"].lower()
        url = r["url"].lower()
        if kind == "mai" and ("maison" in title or "pred-mai" in url):
            return r["url"]
        if kind == "app" and "pred-app-" in url:
            return r["url"]
        # repli sur le libellé exact « appartement » (sans « pièces »)
        if kind == "app" and "loyer appartement" in title and "pièce" not in title:
            return r["url"]
    raise RuntimeError(f"loyers {year}/{kind} introuvable")


def build(con, dept: str | None = None) -> None:
    con.execute("""
        CREATE OR REPLACE TEMP TABLE loyers_raw (
            code_arr VARCHAR, annee SMALLINT, metric VARCHAR, valeur DOUBLE
        )
    """)
    for year in YEARS:
        for kind, metric in (("mai", "loyer_maison_m2"), ("app", "loyer_appart_m2")):
            csv = download(_resolve(year, kind), f"loyers/{year}_{kind}.csv")
            csv = _to_utf8(csv)  # certains millésimes sont en latin-1, rejeté par DuckDB
            con.execute(f"""
                INSERT INTO loyers_raw
                SELECT INSEE_C, {year}, '{metric}',
                       TRY_CAST(replace(loypredm2, ',', '.') AS DOUBLE)
                FROM read_csv('{csv}', delim = ';', header = true, all_varchar = true,
                              quote = '"', escape = '"', strict_mode = false)
                WHERE TRY_CAST(replace(loypredm2, ',', '.') AS DOUBLE) IS NOT NULL
            """)

    where_dept = f"WHERE {remap_plm('code_arr')} LIKE '{dept}%'" if dept else ""
    replace_source(con, "loyers", f"""
        SELECT {remap_plm('code_arr')} AS code_insee, annee, metric, avg(valeur) AS valeur
        FROM loyers_raw {where_dept}
        GROUP BY 1, 2, 3
    """)
