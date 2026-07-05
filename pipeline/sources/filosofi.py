"""FiLoSoFi (INSEE, revenus localisés sociaux et fiscaux) → par commune :
- revenu_median : médiane du niveau de vie annuel par unité de consommation (€)
- taux_pauvrete : part de la population sous le seuil de pauvreté (60 % du médian, %)

Dernier millésime disponible : 2021 (le 2022 n'a pas pu être produit par l'INSEE).
Une seule année → pas de tendance, mais un indicateur de niveau de vie fort et
disponible pour presque toutes les communes.
"""

from __future__ import annotations

import zipfile

from common import DATA, download, remap_plm, replace_source

URL = "https://www.insee.fr/fr/statistiques/fichier/7756729/base-cc-filosofi-2021-geo2025_csv.zip"
MEASURES = {"MED_SL": "revenu_median", "PR_MD60": "taux_pauvrete"}


def build(con, dept: str | None = None) -> None:
    zip_path = download(URL, "filosofi/filosofi_2021.zip")
    out_dir = DATA / "filosofi" / "extrait"
    if not out_dir.exists():
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(out_dir)
    csv = next(p for p in out_dir.iterdir() if p.name.endswith("_data.csv"))

    where_dept = f"AND {remap_plm('GEO')} LIKE '{dept}%'" if dept else ""
    cases = " ".join(f"WHEN '{k}' THEN '{v}'" for k, v in MEASURES.items())
    replace_source(con, "filosofi", f"""
        SELECT {remap_plm('GEO')} AS code_insee,
               TIME_PERIOD::SMALLINT AS annee,
               CASE FILOSOFI_MEASURE {cases} END AS metric,
               avg(TRY_CAST(OBS_VALUE AS DOUBLE)) AS valeur
        FROM read_csv('{csv}', delim = ';', header = true, all_varchar = true)
        WHERE GEO_OBJECT = 'COM'
          AND FILOSOFI_MEASURE IN ('{"', '".join(MEASURES)}')
          AND TRY_CAST(OBS_VALUE AS DOUBLE) IS NOT NULL
          {where_dept}
        GROUP BY 1, 2, 3
    """)
