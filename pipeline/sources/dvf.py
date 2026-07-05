"""DVF géolocalisé (Etalab) → prix médian €/m² maisons et terrains à bâtir,
volume de ventes (proxy du dynamisme du marché / des annonces).

geo-dvf publie une fenêtre glissante des 5 dernières années.
Dépend de la table `communes` (étape geometries) pour le taux pour 1000 habitants.
"""

from __future__ import annotations

from common import download, remap_plm, replace_source

BASE = "https://files.data.gouv.fr/geo-dvf/latest/csv"
YEARS = [2021, 2022, 2023, 2024, 2025]


def build(con, dept: str | None = None) -> None:
    files = []
    for year in YEARS:
        if dept:
            url = f"{BASE}/{year}/departements/{dept}.csv.gz"
            name = f"dvf/{year}_{dept}.csv.gz"
        else:
            url = f"{BASE}/{year}/full.csv.gz"
            name = f"dvf/{year}_full.csv.gz"
        files.append(str(download(url, name)))

    file_list = "[" + ", ".join(f"'{f}'" for f in files) + "]"
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE dvf_mut AS
        WITH lignes AS (
            SELECT
                id_mutation,
                year(TRY_CAST(date_mutation AS DATE))::SMALLINT AS annee,
                {remap_plm('code_commune')} AS code_insee,
                nature_mutation,
                type_local,
                nature_culture,
                TRY_CAST(valeur_fonciere AS DOUBLE) AS valeur_fonciere,
                TRY_CAST(surface_reelle_bati AS DOUBLE) AS surface_reelle_bati,
                TRY_CAST(surface_terrain AS DOUBLE) AS surface_terrain
            FROM read_csv({file_list}, all_varchar = true, header = true,
                          delim = ',', quote = '"', escape = '"')
        )
        SELECT
            id_mutation,
            annee,
            code_insee,
            max(valeur_fonciere) AS valeur,
            count(*) FILTER (WHERE type_local = 'Maison') AS nb_lignes_maison,
            count(DISTINCT surface_reelle_bati) FILTER (WHERE type_local = 'Maison') AS nb_surf_maison,
            count(*) FILTER (WHERE type_local IN ('Appartement', 'Local industriel. commercial ou assimilé')) AS nb_autres_locaux,
            max(surface_reelle_bati) FILTER (WHERE type_local = 'Maison') AS surf_maison,
            bool_or(coalesce(surface_reelle_bati, 0) > 0) AS a_bati,
            bool_or(nature_culture ILIKE 'terrains a b%') AS a_terrain_a_batir,
            sum(surface_terrain) AS surf_terrain
        FROM lignes
        WHERE nature_mutation IN ('Vente', 'Vente en l''état futur d''achèvement')
          AND valeur_fonciere > 0 AND annee IS NOT NULL
        GROUP BY 1, 2, 3
    """)

    replace_source(con, "dvf", """
        -- prix médian €/m² des maisons (mutations d'une seule maison, sans appartement/local)
        SELECT code_insee, annee, 'prix_maison_m2' AS metric, median(valeur / surf_maison) AS valeur
        FROM dvf_mut
        WHERE nb_lignes_maison >= 1 AND nb_surf_maison = 1 AND nb_autres_locaux = 0
          AND surf_maison BETWEEN 20 AND 500
          AND valeur / surf_maison BETWEEN 200 AND 20000
        GROUP BY 1, 2

        UNION ALL
        -- prix médian €/m² des terrains à bâtir (mutations sans bâti)
        SELECT code_insee, annee, 'prix_terrain_m2', median(valeur / surf_terrain)
        FROM dvf_mut
        WHERE NOT a_bati AND a_terrain_a_batir AND surf_terrain >= 100
          AND valeur / surf_terrain BETWEEN 1 AND 3000
        GROUP BY 1, 2

        UNION ALL
        -- nombre de ventes (toutes mutations)
        SELECT code_insee, annee, 'nb_ventes', count(*)
        FROM dvf_mut
        GROUP BY 1, 2

        UNION ALL
        -- ventes pour 1000 habitants (dynamisme du marché, comparable entre communes)
        SELECT m.code_insee, m.annee, 'ventes_1000hab', count(*) * 1000.0 / c.population
        FROM dvf_mut m JOIN communes c USING (code_insee)
        WHERE c.population > 0
        GROUP BY 1, 2, c.population
    """)
