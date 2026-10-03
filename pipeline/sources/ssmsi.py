"""Délinquance enregistrée (SSMSI, base communale 2016→) → faits pour 1000 habitants.

Périmètre du score `delits_1000hab` : violences, vols, cambriolages, destructions
(hors stupéfiants et escroqueries en ligne, peu liés à la sécurité locale ressentie).
Les cellules sous secret statistique (`ndiff`) sont remplacées par l'estimation
fournie par le SSMSI (`complement_info_nombre`).
Sous-indicateurs exportés pour la fiche : violences, vols, cambriolages.
"""

from __future__ import annotations

import re

from common import datagouv_resources, download, replace_source

DATASET = "bases-statistiques-communale-departementale-et-regionale-de-la-delinquance-enregistree-par-la-police-et-la-gendarmerie-nationales"

BASKET = (
    "'Violences physiques intrafamiliales', 'Violences physiques hors cadre familial', "
    "'Violences sexuelles', 'Vols avec armes', 'Vols violents sans arme', "
    "'Vols sans violence contre des personnes', 'Vols de véhicule', "
    "'Vols dans les véhicules', 'Vols d''accessoires sur véhicules', "
    "'Cambriolages de logement', 'Destructions et dégradations volontaires'"
)


def _resolve_url() -> str:
    for r in datagouv_resources(DATASET):
        if r["format"] == "parquet" and "COM" in r["title"] and "COMPL" not in r["title"]:
            return r["url"]
    raise RuntimeError("ressource parquet communale SSMSI introuvable")


def build(con, dept: str | None = None) -> None:
    parquet = download(_resolve_url(), "ssmsi/delinquance_communale.parquet")
    # La colonne du code commune porte le millésime du code officiel géographique
    # (CODGEO_2025, puis CODGEO_2026 après les fusions de communes) : on la cherche.
    cols = [c[0] for c in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{parquet}')").fetchall()]
    geo = next((c for c in cols if re.fullmatch(r"CODGEO_\d{4}", c)), None)
    if geo is None:
        raise RuntimeError(f"SSMSI : colonne CODGEO_<année> introuvable parmi {cols}")
    where_dept = f"AND {geo} LIKE '{dept}%'" if dept else ""
    # la base contient à la fois les arrondissements de Paris/Lyon/Marseille ET
    # l'agrégat commune (75056, 13055, 69123) : on exclut les arrondissements
    base = f"""
        SELECT {geo} AS code_insee, annee,
               coalesce(nombre, complement_info_nombre) AS faits,
               insee_pop, indicateur
        FROM read_parquet('{parquet}')
        WHERE insee_pop > 0 {where_dept}
          AND NOT ({geo} BETWEEN '75101' AND '75120'
                   OR {geo} BETWEEN '13201' AND '13216'
                   OR {geo} BETWEEN '69381' AND '69389')
    """
    replace_source(con, "ssmsi", f"""
        WITH base AS ({base})
        SELECT code_insee, annee, 'delits_1000hab' AS metric,
               1000.0 * sum(faits) / max(insee_pop) AS valeur
        FROM base WHERE indicateur IN ({BASKET}) GROUP BY 1, 2

        UNION ALL
        SELECT code_insee, annee, 'violences_1000hab',
               1000.0 * sum(faits) / max(insee_pop)
        FROM base WHERE indicateur LIKE 'Violences%' GROUP BY 1, 2

        UNION ALL
        SELECT code_insee, annee, 'vols_1000hab',
               1000.0 * sum(faits) / max(insee_pop)
        FROM base WHERE indicateur LIKE 'Vols%' GROUP BY 1, 2

        UNION ALL
        SELECT code_insee, annee, 'cambriolages_1000hab',
               1000.0 * sum(faits) / max(insee_pop)
        FROM base WHERE indicateur = 'Cambriolages de logement' GROUP BY 1, 2
    """)
