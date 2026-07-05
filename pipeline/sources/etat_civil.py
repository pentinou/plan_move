"""État civil INSEE (API Melodi) → naissances et décès annuels par commune,
solde naturel pour 1000 habitants (dynamisme démographique).

Le solde est rapporté à la population légale actuelle (approximation :
l'historique de population n'est pas chargé).
Dépend de la table `communes` (étape geometries).
"""

from __future__ import annotations

import zipfile

from common import DATA, download, replace_source

NAIS_URL = "https://api.insee.fr/melodi/file/DS_ETAT_CIVIL_NAIS_COMMUNES/DS_ETAT_CIVIL_NAIS_COMMUNES_CSV_FR"
DECES_URL = "https://api.insee.fr/melodi/file/DS_ETAT_CIVIL_DECES_COMMUNES/DS_ETAT_CIVIL_DECES_COMMUNES_CSV_FR"


def _data_csv(url: str, name: str) -> str:
    zip_path = download(url, f"etat_civil/{name}.zip")
    out_dir = DATA / "etat_civil" / name
    if not out_dir.exists():
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(out_dir)
    csvs = [p for p in out_dir.iterdir() if p.name.endswith("_data.csv")]
    if not csvs:
        raise RuntimeError(f"pas de fichier _data.csv dans {zip_path}")
    return str(csvs[0])


def build(con, dept: str | None = None) -> None:
    nais_csv = _data_csv(NAIS_URL, "naissances")
    deces_csv = _data_csv(DECES_URL, "deces")
    where_dept = f"AND GEO LIKE '{dept}%'" if dept else ""

    for table, csv in (("ec_nais", nais_csv), ("ec_deces", deces_csv)):
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE {table} AS
            SELECT GEO AS code_insee, TIME_PERIOD::SMALLINT AS annee, OBS_VALUE::DOUBLE AS n
            FROM read_csv('{csv}', delim = ';', header = true, all_varchar = true)
            WHERE GEO_OBJECT = 'COM' {where_dept}
        """)

    replace_source(con, "etat_civil", """
        SELECT code_insee, annee, 'naissances' AS metric, n AS valeur FROM ec_nais

        UNION ALL
        SELECT code_insee, annee, 'deces', n FROM ec_deces

        UNION ALL
        SELECT
            coalesce(na.code_insee, de.code_insee) AS code_insee,
            coalesce(na.annee, de.annee) AS annee,
            'solde_naturel',
            (coalesce(na.n, 0) - coalesce(de.n, 0)) * 1000.0 / c.population
        FROM ec_nais na
        FULL JOIN ec_deces de USING (code_insee, annee)
        JOIN communes c ON c.code_insee = coalesce(na.code_insee, de.code_insee)
        WHERE c.population > 0
    """)
