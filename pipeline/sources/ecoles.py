"""Écoles, collèges et lycées (data.education.gouv.fr) :
- nb_ecoles : écoles maternelles/élémentaires ouvertes à ≤10 km du centre de la commune
- ips_ecoles : IPS moyen des écoles de la commune (sinon, école la plus proche ≤30 km)
- reussite_dnb / va_college : réussite au brevet et valeur ajoutée des collèges de la
  commune (sinon, collège le plus proche ≤30 km — la sectorisation officielle n'est
  pas en open data national)
- reussite_bac : taux de réussite au bac des lycées généraux et technologiques de la
  commune (sinon, lycée le plus proche ≤30 km)
"""

from __future__ import annotations

import json

import numpy as np
from scipy.spatial import cKDTree

from common import WEB_DATA, download, remap_plm, replace_source

ODS = "https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/{}/exports/parquet"
RAYON_ECOLES_M = 10_000
RAYON_FALLBACK_M = 30_000
ANNEE_ANNUAIRE = 2025  # l'annuaire est une photographie actuelle, sans historique

RAYON_TERRE = 6_371_000.0


def _xy(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Projection équirectangulaire locale en mètres — précise pour des distances ≤30 km,
    y compris outre-mer (contrairement au Lambert-93)."""
    lat_r = np.radians(lat)
    return np.column_stack((np.radians(lon) * RAYON_TERRE * np.cos(lat_r), lat_r * RAYON_TERRE))


def build(con, dept: str | None = None) -> None:
    annuaire = download(ODS.format("fr-en-annuaire-education"), "ecoles/annuaire.parquet")
    ips = download(ODS.format("fr-en-ips-ecoles-ap2022"), "ecoles/ips_ecoles.parquet")
    ivac = download(ODS.format("fr-en-indicateurs-valeur-ajoutee-colleges"), "ecoles/ivac_colleges.parquet")
    ival = download(ODS.format("fr-en-indicateurs-de-resultat-des-lycees-gt_v2"), "ecoles/ival_lycees.parquet")

    where_dept = f"WHERE dept = '{dept}'" if dept else ""
    communes = con.execute(f"SELECT code_insee, lon, lat FROM communes {where_dept}").fetchall()
    codes = [c[0] for c in communes]
    cxy = _xy(np.array([c[1] for c in communes]), np.array([c[2] for c in communes]))

    con.execute("""
        CREATE OR REPLACE TEMP TABLE ecoles_out (
            code_insee VARCHAR, annee SMALLINT, metric VARCHAR, valeur DOUBLE
        )
    """)
    con.execute("CREATE OR REPLACE TEMP TABLE scope (code_insee VARCHAR)")
    con.executemany("INSERT INTO scope VALUES (?)", [(c,) for c in codes])

    # --- nb_ecoles : comptage dans un rayon de 10 km ---
    rows = con.execute(f"""
        SELECT TRY_CAST(longitude AS DOUBLE), TRY_CAST(latitude AS DOUBLE)
        FROM read_parquet('{annuaire}')
        WHERE type_etablissement = 'Ecole' AND etat = 'OUVERT'
          AND (TRY_CAST(ecole_maternelle AS INT) = 1 OR TRY_CAST(ecole_elementaire AS INT) = 1)
          AND longitude IS NOT NULL AND latitude IS NOT NULL
    """).fetchall()
    exy = _xy(np.array([r[0] for r in rows]), np.array([r[1] for r in rows]))
    counts = cKDTree(exy).query_ball_point(cxy, r=RAYON_ECOLES_M, return_length=True)
    con.executemany(
        "INSERT INTO ecoles_out VALUES (?, ?, 'nb_ecoles', ?)",
        [(code, ANNEE_ANNUAIRE, int(n)) for code, n in zip(codes, counts)],
    )
    print(f"  [ecoles] {len(rows)} écoles géolocalisées (rayon {RAYON_ECOLES_M // 1000} km)")

    # --- ips_ecoles : moyenne communale par rentrée ---
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE ips_uai AS
        SELECT uai, left(rentree_scolaire, 4)::SMALLINT AS annee, TRY_CAST(ips AS DOUBLE) AS ips,
               {remap_plm('code_insee_de_la_commune')} AS code_insee
        FROM read_parquet('{ips}')
        WHERE TRY_CAST(ips AS DOUBLE) IS NOT NULL
    """)
    con.execute("""
        INSERT INTO ecoles_out
        SELECT code_insee, annee, 'ips_ecoles', avg(ips)
        FROM ips_uai JOIN scope USING (code_insee)
        GROUP BY 1, 2
    """)

    # --- reussite_dnb / va_college : collèges de la commune ---
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE colleges AS
        SELECT v.uai,
               year(v.session)::SMALLINT AS annee,
               TRY_CAST(v.taux_de_reussite_g AS DOUBLE) AS taux,
               TRY_CAST(v.va_du_taux_de_reussite_g AS DOUBLE) AS va,
               {remap_plm('a.code_commune')} AS code_insee,
               TRY_CAST(a.longitude AS DOUBLE) AS lon,
               TRY_CAST(a.latitude AS DOUBLE) AS lat
        FROM read_parquet('{ivac}') v
        JOIN read_parquet('{annuaire}') a ON a.identifiant_de_l_etablissement = v.uai
        WHERE TRY_CAST(v.taux_de_reussite_g AS DOUBLE) IS NOT NULL
    """)
    con.execute("""
        INSERT INTO ecoles_out
        SELECT code_insee, annee, 'reussite_dnb', avg(taux)
        FROM colleges JOIN scope USING (code_insee) GROUP BY 1, 2
    """)
    con.execute("""
        INSERT INTO ecoles_out
        SELECT code_insee, annee, 'va_college', avg(va)
        FROM colleges JOIN scope USING (code_insee)
        WHERE va IS NOT NULL GROUP BY 1, 2
    """)

    # --- reussite_bac : lycées généraux et technologiques de la commune ---
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE lycees AS
        SELECT v.uai,
               coalesce(TRY_CAST(TRY_CAST(v.annee AS VARCHAR) AS SMALLINT),
                        year(TRY_CAST(v.annee AS DATE)))::SMALLINT AS annee,
               TRY_CAST(v.taux_reu_total AS DOUBLE) AS taux,
               {remap_plm('v.code_commune')} AS code_insee,
               TRY_CAST(a.longitude AS DOUBLE) AS lon,
               TRY_CAST(a.latitude AS DOUBLE) AS lat
        FROM read_parquet('{ival}') v
        LEFT JOIN read_parquet('{annuaire}') a ON a.identifiant_de_l_etablissement = v.uai
        WHERE TRY_CAST(v.taux_reu_total AS DOUBLE) IS NOT NULL
    """)
    con.execute("""
        INSERT INTO ecoles_out
        SELECT code_insee, annee, 'reussite_bac', avg(taux)
        FROM lycees JOIN scope USING (code_insee) GROUP BY 1, 2
    """)

    # --- replis « établissement le plus proche » pour les communes sans données ---
    _fallback_nearest(
        con, codes, cxy, metric="ips_ecoles",
        points_sql=f"""
            SELECT i.uai, TRY_CAST(a.longitude AS DOUBLE), TRY_CAST(a.latitude AS DOUBLE)
            FROM (SELECT uai, max(annee) FROM ips_uai GROUP BY uai) i
            JOIN read_parquet('{annuaire}') a ON a.identifiant_de_l_etablissement = i.uai
            WHERE a.longitude IS NOT NULL AND a.latitude IS NOT NULL
        """,
        series_sql="SELECT uai, annee, ips FROM ips_uai",
    )
    _fallback_nearest(
        con, codes, cxy, metric="reussite_dnb",
        points_sql="""
            SELECT uai, any_value(lon), any_value(lat) FROM colleges
            WHERE lon IS NOT NULL AND lat IS NOT NULL GROUP BY uai
        """,
        series_sql="SELECT uai, annee, taux FROM colleges",
        extra=("va_college", "SELECT uai, annee, va FROM colleges WHERE va IS NOT NULL"),
    )
    _fallback_nearest(
        con, codes, cxy, metric="reussite_bac",
        points_sql="""
            SELECT uai, any_value(lon), any_value(lat) FROM lycees
            WHERE lon IS NOT NULL AND lat IS NOT NULL GROUP BY uai
        """,
        series_sql="SELECT uai, annee, taux FROM lycees WHERE annee IS NOT NULL",
    )

    replace_source(
        con, "ecoles",
        "SELECT * FROM ecoles_out WHERE annee IS NOT NULL AND valeur IS NOT NULL",
    )
    _export_listes_ecoles(con, annuaire)


def _export_listes_ecoles(con, annuaire) -> None:
    """web/public/data/ecoles/{dept}.json : par commune, la liste des écoles
    maternelles/élémentaires ouvertes (nom, niveaux, secteur, IPS dernière rentrée)."""
    rows = con.execute(f"""
        WITH ips_last AS (SELECT uai, arg_max(ips, annee) AS ips FROM ips_uai GROUP BY uai)
        SELECT {remap_plm('a.code_commune')}, a.nom_etablissement,
               TRY_CAST(a.ecole_maternelle AS INT), TRY_CAST(a.ecole_elementaire AS INT),
               a.statut_public_prive, i.ips
        FROM read_parquet('{annuaire}') a
        LEFT JOIN ips_last i ON i.uai = a.identifiant_de_l_etablissement
        WHERE a.type_etablissement = 'Ecole' AND a.etat = 'OUVERT'
          AND (TRY_CAST(a.ecole_maternelle AS INT) = 1 OR TRY_CAST(a.ecole_elementaire AS INT) = 1)
        ORDER BY a.nom_etablissement
    """).fetchall()
    by_dept: dict[str, dict] = {}
    for code, nom, mat, ele, statut, ips_v in rows:
        if not code:
            continue
        d = code[:3] if code.startswith("97") else code[:2]
        by_dept.setdefault(d, {}).setdefault(code, []).append(
            [nom, int(mat or 0), int(ele or 0), statut or "", None if ips_v is None else round(ips_v, 1)]
        )
    out_dir = WEB_DATA / "ecoles"
    out_dir.mkdir(parents=True, exist_ok=True)
    for d, data in by_dept.items():
        (out_dir / f"{d}.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print(f"  [ecoles] listes d'écoles : {len(by_dept)} départements")


def _fallback_nearest(con, codes, cxy, *, metric, points_sql, series_sql, extra=None) -> None:
    """Pour les communes sans valeur pour `metric`, reprend la série annuelle de
    l'établissement le plus proche (≤30 km)."""
    have = {r[0] for r in con.execute(
        "SELECT DISTINCT code_insee FROM ecoles_out WHERE metric = ?", [metric]
    ).fetchall()}
    missing = [i for i, code in enumerate(codes) if code not in have]
    if not missing:
        return

    points = con.execute(points_sql).fetchall()
    uais = [p[0] for p in points]
    pxy = _xy(np.array([p[1] for p in points]), np.array([p[2] for p in points]))
    dists, idx = cKDTree(pxy).query(cxy[missing], k=1, distance_upper_bound=RAYON_FALLBACK_M)

    series: dict[str, list] = {}
    for uai, annee, val in con.execute(series_sql).fetchall():
        series.setdefault(uai, []).append((annee, val))
    extra_series: dict[str, list] = {}
    if extra:
        for uai, annee, val in con.execute(extra[1]).fetchall():
            extra_series.setdefault(uai, []).append((annee, val))

    rows = []
    matched = 0
    for pos, (d, j) in enumerate(zip(dists, idx)):
        if not np.isfinite(d):
            continue  # aucun établissement à ≤30 km (îles, communes très isolées)
        code = codes[missing[pos]]
        uai = uais[j]
        matched += 1
        rows += [(code, annee, metric, val) for annee, val in series.get(uai, [])]
        if extra:
            rows += [(code, annee, extra[0], val) for annee, val in extra_series.get(uai, [])]
    con.executemany("INSERT INTO ecoles_out VALUES (?, ?, ?, ?)", rows)
    print(f"  [ecoles] repli {metric} : {matched}/{len(missing)} communes sans donnée locale")
