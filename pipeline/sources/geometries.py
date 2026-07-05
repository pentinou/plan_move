"""Contours communaux (Etalab / Admin Express COG) → communes.pmtiles
+ table de référence `communes` (code INSEE, nom, département, population, centre)."""

from __future__ import annotations

import gzip
import json
import shutil
import subprocess

from common import DATA, WEB_DATA, download, tippecanoe_bin

CONTOURS_URL = "https://etalab-datasets.geo.data.gouv.fr/contours-administratifs/latest/geojson/communes-50m.geojson.gz"
DEPARTEMENTS_URL = "https://etalab-datasets.geo.data.gouv.fr/contours-administratifs/latest/geojson/departements-100m.geojson.gz"
GEO_API_URL = "https://geo.api.gouv.fr/communes?fields=code,nom,population,centre,codeDepartement&format=json"


def _gunzip(src, dest):
    if dest.exists():
        return dest
    with gzip.open(src, "rb") as f_in, open(dest, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    return dest


def _est_arrondissement(code: str) -> bool:
    return (
        "75101" <= code <= "75120" or "13201" <= code <= "13216" or "69381" <= code <= "69389"
    )


def _filtrer_arrondissements(src, dest):
    """Le fichier de contours contient Paris/Lyon/Marseille ET leurs arrondissements
    municipaux, superposés : on ne garde que les communes entières."""
    if dest.exists():
        return dest
    geo = json.loads(src.read_text())
    avant = len(geo["features"])
    geo["features"] = [f for f in geo["features"] if not _est_arrondissement(f["properties"]["code"])]
    dest.write_text(json.dumps(geo, separators=(",", ":")))
    print(f"  [communes] {avant - len(geo['features'])} arrondissements municipaux retirés des contours")
    return dest


def build(con, dept: str | None = None) -> None:
    # 1. Table de référence des communes (toujours France entière : la carte l'exige)
    geo_json = download(GEO_API_URL, "communes_geo_api.json")
    con.execute("""
        CREATE OR REPLACE TABLE communes AS
        SELECT
            code                                   AS code_insee,
            nom,
            codeDepartement                        AS dept,
            population::INTEGER                    AS population,
            centre.coordinates[1]::DOUBLE          AS lon,
            centre.coordinates[2]::DOUBLE          AS lat
        FROM read_json(?)
    """, [str(geo_json)])
    n = con.execute("SELECT count(*) FROM communes").fetchone()[0]
    print(f"  [communes] table de référence : {n} communes")

    # 2. Contours départementaux (surcouche de la carte, servie en GeoJSON brut)
    WEB_DATA.mkdir(parents=True, exist_ok=True)
    dep_gz = download(DEPARTEMENTS_URL, "departements-100m.geojson.gz")
    _gunzip(dep_gz, WEB_DATA / "departements.geojson")

    # 3. Tuiles vectorielles des communes (long : ~2 min, sauté si déjà à jour)
    out = WEB_DATA / "communes.pmtiles"
    contours_gz = download(CONTOURS_URL, "communes-50m.geojson.gz")
    brut = _gunzip(contours_gz, DATA / "communes-50m.geojson")
    contours = _filtrer_arrondissements(brut, DATA / "communes-50m-filtre.geojson")
    if out.exists() and out.stat().st_mtime > contours.stat().st_mtime:
        print("  [communes] communes.pmtiles déjà à jour")
        return
    subprocess.run(
        [
            tippecanoe_bin(),
            "-o", str(out),
            "--layer=communes",
            "--minimum-zoom=4",
            "--maximum-zoom=11",
            "--coalesce-densest-as-needed",
            "--extend-zooms-if-still-dropping",
            "--detect-shared-borders",
            "--quiet",
            "--force",
            str(contours),
        ],
        check=True,
    )
    print(f"  [communes] {out.name} généré ({out.stat().st_size / 1e6:.1f} Mo)")
