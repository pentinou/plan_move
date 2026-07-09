"""Hôpitaux et cliniques MCO (FINESS géolocalisé + e-Satis HAS) :
- dist_hopital : distance (km) du centre de la commune à l'établissement MCO le
  plus proche (établissements du recueil e-Satis « hospitalisation +48h », le
  périmètre obligatoire couvre tous les hôpitaux/cliniques avec hospitalisation
  complète en médecine-chirurgie-obstétrique)
- note_hopital : score de satisfaction des patients e-Satis (/100, ajusté HAS) de
  l'établissement noté le plus proche ; recueils 2022-2025 → série pour la tendance

Il n'existe pas de « classement » officiel des hôpitaux en open data (le palmarès
du Point est propriétaire) : e-Satis est la note publique de la HAS.
Le FINESS géolocalisé code les coordonnées dans des projections locales (Lambert-93
en métropole, UTM outre-mer) indiquées ligne à ligne → reprojection pyproj.
"""

from __future__ import annotations

import csv
import re

import numpy as np
from pyproj import Transformer
from scipy.spatial import cKDTree

from common import datagouv_resources, download, replace_source
from sources.ecoles import _xy

FINESS = "finess-extraction-du-fichier-des-etablissements"
ESATIS = {
    2022: "https://static.data.gouv.fr/resources/indicateurs-de-qualite-et-de-securite-des-soins-recueil-2022/20230105-144901/resultats-iqss-esatis48h-mco-open-data-2022.xlsx",
    2023: "https://static.data.gouv.fr/resources/indicateurs-de-qualite-et-de-securite-des-soins-recueil-2023/20231211-153347/resultats-iqss-esatis48h-mco-open-data-2023.xlsx",
    2024: "https://static.data.gouv.fr/resources/indicateurs-de-qualite-et-de-securite-des-soins-recueil-2024/20241029-142506/resultats-iqss-esatis48h-mco-open-data-2024.xlsx",
    2025: "https://static.data.gouv.fr/resources/indicateurs-de-qualite-et-de-securite-des-soins-recueil-2025/20251031-141235/resultats-iqss-esatis48h-mco-open-data-2025.xlsx",
}
DERNIER = max(ESATIS)


def _resolve_finess() -> str:
    for r in datagouv_resources(FINESS):
        if "géolocalisés" in r["title"]:
            return r["url"]
    raise RuntimeError("extraction FINESS géolocalisée introuvable")


def _finess_lonlat(path) -> dict[str, tuple[float, float]]:
    """N° FINESS établissement → (lon, lat). Le fichier concatène deux sections ;
    les lignes `geolocalisation` portent x, y et le code EPSG source."""
    by_epsg: dict[str, list[tuple[str, float, float]]] = {}
    with open(path, encoding="latin-1") as f:
        for row in csv.reader(f, delimiter=";"):
            if row[0] != "geolocalisation":
                continue
            m = re.search(r"EPSG:(\d+)", row[4])
            try:
                x, y = float(row[2]), float(row[3])
            except ValueError:
                continue
            if m:
                by_epsg.setdefault(m.group(1), []).append((row[1], x, y))
    out: dict[str, tuple[float, float]] = {}
    for epsg, rows in by_epsg.items():
        tr = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
        lons, lats = tr.transform([r[1] for r in rows], [r[2] for r in rows])
        out.update((r[0], (lon, lat)) for r, lon, lat in zip(rows, lons, lats))
    return out


def build(con, dept: str | None = None) -> None:
    finess_csv = download(_resolve_finess(), "hopitaux/finess_geo.csv")
    lonlat = _finess_lonlat(finess_csv)
    print(f"  [hopitaux] {len(lonlat)} établissements FINESS géolocalisés")

    # scores e-Satis par établissement (FINESS géographique) et par recueil
    con.execute("INSTALL excel; LOAD excel;")
    scores: dict[str, dict[int, float]] = {}
    etabs_dernier: set[str] = set()
    for annee, url in ESATIS.items():
        xlsx = download(url, f"hopitaux/esatis48h_{annee}.xlsx")
        for fin, score in con.execute(f"""
            SELECT finess_geo, TRY_CAST(score_all_rea_ajust AS DOUBLE)
            FROM read_xlsx('{xlsx}', all_varchar = true)
            WHERE finess_geo IS NOT NULL
        """).fetchall():
            if annee == DERNIER:
                etabs_dernier.add(fin)
            if score is not None:
                scores.setdefault(fin, {})[annee] = score

    # deux arbres : tous les établissements MCO du dernier recueil (distance),
    # et ceux qui ont au moins un score (note)
    mco = [f for f in etabs_dernier if f in lonlat]
    notes = [f for f in scores if f in lonlat]
    print(f"  [hopitaux] {len(mco)} établissements MCO localisés, {len(notes)} notés")
    mco_xy = _xy(np.array([lonlat[f][0] for f in mco]), np.array([lonlat[f][1] for f in mco]))
    notes_xy = _xy(np.array([lonlat[f][0] for f in notes]), np.array([lonlat[f][1] for f in notes]))

    where_dept = f"WHERE dept = '{dept}'" if dept else ""
    communes = con.execute(f"SELECT code_insee, lon, lat FROM communes {where_dept}").fetchall()
    cxy = _xy(np.array([c[1] for c in communes]), np.array([c[2] for c in communes]))

    dists, _ = cKDTree(mco_xy).query(cxy, k=1)
    _, idx_note = cKDTree(notes_xy).query(cxy, k=1)

    rows = []
    for (code, _, _), d, j in zip(communes, dists, idx_note):
        rows.append((code, DERNIER, "dist_hopital", float(d) / 1000))
        rows += [
            (code, annee, "note_hopital", score)
            for annee, score in scores[notes[j]].items()
        ]
    con.execute("""
        CREATE OR REPLACE TEMP TABLE hopitaux_out (
            code_insee VARCHAR, annee SMALLINT, metric VARCHAR, valeur DOUBLE
        )
    """)
    con.executemany("INSERT INTO hopitaux_out VALUES (?, ?, ?, ?)", rows)
    replace_source(con, "hopitaux", "SELECT * FROM hopitaux_out")
