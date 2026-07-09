"""Taux de logements sociaux (RPLS, via l'open data de la Caisse des Dépôts) :
- part_logements_sociaux : logements sociaux (hors habitat spécifique et parc non
  conventionné des SEM) rapportés aux résidences principales, en %. À rapprocher
  des 20-25 % exigés par la loi SRU dans les communes concernées : une commune
  nettement sous le seuil devra construire du logement social.

Dataset arrêté au 01/01/2025 (millésime unique ≈ 2024, pas de tendance) ; les
codes PLM y sont déjà agrégés (75056/13055/69123).
"""

from __future__ import annotations

from common import download, replace_source

URL = (
    "https://opendata.caissedesdepots.fr/api/explore/v2.1/catalog/datasets/"
    "logements-sociaux-dans-les-communes/exports/csv"
    "?select=code_commune,taux_de_logements_sociaux&delimiter=%3B"
)
ANNEE = 2024


def build(con, dept: str | None = None) -> None:
    csv = download(URL, "logement_social/taux_lls.csv")
    where_dept = f"AND code_commune LIKE '{dept}%'" if dept else ""
    replace_source(con, "logement_social", f"""
        SELECT code_commune AS code_insee, {ANNEE} AS annee,
               'part_logements_sociaux' AS metric,
               TRY_CAST(taux_de_logements_sociaux AS DOUBLE) AS valeur
        FROM read_csv('{csv}', delim = ';', header = true, all_varchar = true)
        WHERE TRY_CAST(taux_de_logements_sociaux AS DOUBLE) IS NOT NULL
          {where_dept}
    """)
