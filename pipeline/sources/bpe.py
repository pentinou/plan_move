"""Base permanente des équipements (INSEE, millésime 2024) :
- medecins_10khab : médecins généralistes (D265) pour 10 000 habitants
- nb_creches : établissements d'accueil du jeune enfant (D502)
- equip_loisirs_10khab : équipements de loisirs pour 10 000 habitants — cinéma,
  bibliothèque, conservatoire, exposition/musée, arts du spectacle, bassin de
  natation, salle de remise en forme, salle multisports/gymnase

Le fichier ne liste que les communes équipées : l'absence vaut 0 (LEFT JOIN depuis
la table communes). Il contient plusieurs granularités (COM, ARM, EPCI…) → ne
garder que GEO_OBJECT = 'COM' (les agrégats PLM 75056/13055/69123 y sont déjà).
"""

from __future__ import annotations

import zipfile

from common import DATA, download, replace_source

URL = "https://www.insee.fr/fr/statistiques/fichier/8217527/DS_BPE_CSV_FR.zip"
ANNEE = 2024
LOISIRS = ("F303", "F305", "F307", "F312", "F315", "F101", "F120", "F121")


def build(con, dept: str | None = None) -> None:
    zip_path = download(URL, "bpe/DS_BPE_CSV_FR.zip")
    out_dir = DATA / "bpe" / "extrait"
    if not out_dir.exists():
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(out_dir)
    csv = next(p for p in out_dir.iterdir() if p.name.endswith("_data.csv"))

    where_dept = f"AND code_insee LIKE '{dept}%'" if dept else ""
    loisirs_in = "', '".join(LOISIRS)
    replace_source(con, "bpe", f"""
        WITH bpe AS (
            SELECT GEO AS code_insee, FACILITY_TYPE AS typ,
                   sum(TRY_CAST(OBS_VALUE AS DOUBLE)) AS n
            FROM read_csv('{csv}', delim = ';', header = true, all_varchar = true)
            WHERE GEO_OBJECT = 'COM' AND BPE_MEASURE = 'FACILITIES'
              AND FACILITY_TYPE IN ('D265', 'D502', '{loisirs_in}')
            GROUP BY 1, 2
        ),
        com AS (
            SELECT code_insee, population FROM communes
            WHERE population > 0 {where_dept}
        )
        SELECT c.code_insee, {ANNEE} AS annee, 'medecins_10khab' AS metric,
               10000.0 * coalesce(b.n, 0) / c.population AS valeur
        FROM com c LEFT JOIN bpe b ON b.code_insee = c.code_insee AND b.typ = 'D265'

        UNION ALL
        SELECT c.code_insee, {ANNEE}, 'nb_creches', coalesce(b.n, 0)
        FROM com c LEFT JOIN bpe b ON b.code_insee = c.code_insee AND b.typ = 'D502'

        UNION ALL
        SELECT c.code_insee, {ANNEE}, 'equip_loisirs_10khab',
               10000.0 * coalesce(sum(b.n), 0) / c.population
        FROM com c LEFT JOIN bpe b ON b.code_insee = c.code_insee
                                  AND b.typ IN ('{loisirs_in}')
        GROUP BY c.code_insee, c.population
    """)
