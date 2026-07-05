"""Arrêts de transport en commun (Point d'accès national, transport.data.gouv.fr) :
- dist_arret_tc : distance (km) du centre de la commune à l'arrêt le plus proche
- nb_arrets_2km : arrêts à ≤2 km du centre (contexte fiche, non scoré)

Le fichier consolidé agrège tous les GTFS publiés ; les doublons entre jeux de
données sont fusionnés par arrondi des coordonnées (~10 m). Photographie actuelle,
pas d'historique.
"""

from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from common import datagouv_resources, download, replace_source
from sources.ecoles import _xy

ANNEE = 2025


def _resolve_url() -> str:
    for r in datagouv_resources("arrets-de-transport-en-france"):
        if r["format"] == "csv":
            return r["url"]
    raise RuntimeError("CSV des arrêts de transport introuvable")


def build(con, dept: str | None = None) -> None:
    stops_csv = download(_resolve_url(), "transports/gtfs_stops.csv")

    stops = con.execute(f"""
        SELECT DISTINCT round(TRY_CAST(stop_lon AS DOUBLE), 4) AS lon,
                        round(TRY_CAST(stop_lat AS DOUBLE), 4) AS lat
        FROM read_csv('{stops_csv}', all_varchar = true, header = true,
                      delim = ',', quote = '"', escape = '"')
        WHERE TRY_CAST(stop_lat AS DOUBLE) BETWEEN -62 AND 62
          AND TRY_CAST(stop_lon AS DOUBLE) BETWEEN -180 AND 180
          AND abs(TRY_CAST(stop_lat AS DOUBLE)) + abs(TRY_CAST(stop_lon AS DOUBLE)) > 0.1
          AND coalesce(location_type, '0') IN ('', '0', '1')
    """).fetchall()
    sxy = _xy(np.array([s[0] for s in stops]), np.array([s[1] for s in stops]))
    tree = cKDTree(sxy)
    print(f"  [transports] {len(stops)} arrêts uniques")

    where_dept = f"WHERE dept = '{dept}'" if dept else ""
    communes = con.execute(f"SELECT code_insee, lon, lat FROM communes {where_dept}").fetchall()
    cxy = _xy(np.array([c[1] for c in communes]), np.array([c[2] for c in communes]))

    dists, _ = tree.query(cxy, k=1)
    counts = tree.query_ball_point(cxy, r=2_000, return_length=True)

    con.execute("""
        CREATE OR REPLACE TEMP TABLE transports_out (
            code_insee VARCHAR, annee SMALLINT, metric VARCHAR, valeur DOUBLE
        )
    """)
    con.executemany(
        "INSERT INTO transports_out VALUES (?, ?, 'dist_arret_tc', ?), (?, ?, 'nb_arrets_2km', ?)",
        [
            (c[0], ANNEE, float(d) / 1000, c[0], ANNEE, int(n))
            for c, d, n in zip(communes, dists, counts)
        ],
    )
    replace_source(con, "transports", "SELECT * FROM transports_out")
