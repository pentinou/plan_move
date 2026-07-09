"""Exporte les agrégats vers web/public/data/ :
- metrics.json : par commune, niveau actuel + tendance (%/an) + percentiles 0-100 par métrique
- series/{dept}.json : séries annuelles complètes par commune (fiche détaillée)

Le registre METRICS est la source de vérité : ordre des colonnes des tableaux compacts
du JSON, sens par défaut (dir=+1 : plus c'est haut mieux c'est), fenêtre de lissage
du niveau (window, en années), décimales d'affichage (dec).
"""

from __future__ import annotations

import datetime
import json

import numpy as np
from scipy.stats import rankdata

from common import WEB_DATA

T_IMMO = "Immobilier & fiscalité"
T_EDUC = "Éducation & petite enfance"
T_SANTE = "Santé"
T_SECU = "Sécurité & niveau de vie"
T_VIE = "Vie locale & dynamisme"

METRICS = [
    dict(id="prix_maison_m2", label="Prix des maisons", unit="€/m²", dir=-1, window=3, dec=0,
         theme=T_IMMO,
         desc="Prix de vente médian des maisons, en € par m², d'après les ventes réelles "
              "enregistrées chez les notaires (base DVF, lissé sur 3 ans). "
              "Ne couvre pas l'Alsace-Moselle ni Mayotte."),
    dict(id="prix_terrain_m2", label="Prix des terrains à bâtir", unit="€/m²", dir=-1, window=3, dec=0,
         theme=T_IMMO,
         desc="Prix de vente médian des terrains à bâtir, en € par m² (ventes réelles, base DVF, "
              "lissé 3 ans). Utile si vous envisagez de faire construire."),
    dict(id="loyer_maison_m2", label="Loyer des maisons", unit="€/m²/mois", dir=-1, window=1, dec=1,
         theme=T_IMMO,
         desc="Loyer mensuel estimé des maisons, en € par m² (Carte des loyers ANIL, construite "
              "sur des millions d'annonces). Exemple : une maison de 100 m² à 10 €/m² "
              "se loue environ 1 000 €/mois."),
    dict(id="loyer_appart_m2", label="Loyer des appartements", unit="€/m²/mois", dir=-1, window=1, dec=1,
         theme=T_IMMO,
         desc="Loyer mensuel estimé des appartements, en € par m² "
              "(Carte des loyers ANIL, d'après les annonces)."),
    dict(id="ventes_1000hab", label="Marché immobilier", unit="ventes/1000 hab/an", dir=1, window=3, dec=1,
         theme=T_IMMO,
         desc="Ventes immobilières par an pour 1 000 habitants (DVF). Mesure la vitalité du "
              "marché local : plus il y a de transactions, plus il y a d'occasions d'acheter."),
    dict(id="taxe_fonciere", label="Taxe foncière (taux communal)", unit="%", dir=-1, window=1, dec=1,
         theme=T_IMMO,
         desc="Taux de taxe foncière sur le bâti voté par la commune (hors parts intercommunale "
              "et ordures ménagères). Il s'applique à la moitié de la valeur locative cadastrale "
              "du bien ; d'une commune à l'autre, l'écart se compte en centaines d'euros par an."),
    dict(id="part_logements_sociaux", label="Logements sociaux (HLM)", unit="%", dir=1, window=1, dec=1,
         theme=T_IMMO,
         desc="Logements sociaux en % des résidences principales (répertoire RPLS). La loi SRU "
              "impose 20 à 25 % aux communes moyennes et grandes : une commune nettement en "
              "dessous devra construire des HLM dans les prochaines années, une commune au-dessus "
              "n'a plus d'obligation."),
    dict(id="nb_creches", label="Crèches (accueil jeune enfant)", unit="établissements", dir=1, window=1, dec=0,
         theme=T_EDUC,
         desc="Établissements d'accueil du jeune enfant dans la commune : crèches collectives et "
              "familiales, micro-crèches, haltes-garderies (BPE INSEE 2024). Nombre brut : les "
              "grandes villes en ont mécaniquement plus."),
    dict(id="nb_ecoles", label="Écoles à ≤10 km", unit="écoles", dir=1, window=1, dec=0,
         theme=T_EDUC,
         desc="Écoles maternelles et élémentaires ouvertes à moins de 10 km à vol d'oiseau du "
              "centre de la commune — l'offre scolaire à proximité, pas seulement dans la "
              "commune elle-même."),
    dict(id="ips_ecoles", label="IPS des écoles", unit="indice", dir=1, window=1, dec=0,
         theme=T_EDUC,
         desc="IPS = Indice de Position Sociale (Éducation nationale) : milieu social moyen des "
              "familles des écoles de la commune, d'environ 50 (très défavorisé) à 185 (très "
              "favorisé), moyenne France ≈ 100. Fortement corrélé aux résultats scolaires. Sans "
              "école dans la commune, c'est l'école la plus proche (≤ 30 km) qui est retenue."),
    dict(id="reussite_dnb", label="Réussite au brevet", unit="%", dir=1, window=3, dec=1,
         theme=T_EDUC,
         desc="Taux de réussite au brevet des collèges de la commune, lissé 3 ans — ou du collège "
              "le plus proche (≤ 30 km) si elle n'en a pas (la carte scolaire n'est pas en "
              "open data)."),
    dict(id="reussite_bac", label="Réussite au bac", unit="%", dir=1, window=3, dec=1,
         theme=T_EDUC,
         desc="Taux de réussite au bac des lycées généraux et technologiques de la commune "
              "(ou du plus proche à défaut), lissé 3 ans."),
    dict(id="va_college", label="Valeur ajoutée du collège", unit="pts", dir=1, window=3, dec=1,
         theme=T_EDUC,
         desc="Écart entre le taux de réussite au brevet obtenu et celui attendu compte tenu du "
              "profil social des élèves. Positif = le collège fait mieux que prévu. Complète "
              "l'IPS : un collège populaire peut avoir une forte valeur ajoutée."),
    dict(id="medecins_10khab", label="Médecins généralistes", unit="/10 000 hab", dir=1, window=1, dec=1,
         theme=T_SANTE,
         desc="Médecins généralistes exerçant dans la commune, pour 10 000 habitants "
              "(BPE INSEE 2024), moyenne France ≈ 9. Un 0 dans une petite commune n'est pas "
              "forcément un désert médical : regardez les communes voisines."),
    dict(id="dist_hopital", label="Distance à l'hôpital", unit="km", dir=-1, window=1, dec=1,
         theme=T_SANTE,
         desc="Distance à vol d'oiseau au plus proche hôpital ou clinique pratiquant "
              "l'hospitalisation complète (médecine, chirurgie, obstétrique) — le temps d'accès "
              "aux urgences et à la maternité en dépend."),
    dict(id="note_hopital", label="Satisfaction de l'hôpital le plus proche", unit="/100", dir=1, window=3, dec=1,
         theme=T_SANTE,
         desc="Satisfaction des patients hospitalisés plus de 48 h dans l'hôpital le plus "
              "proche : score e-Satis de la Haute Autorité de Santé, sur 100 (moyenne "
              "nationale ≈ 74). C'est la seule note officielle publique — il n'existe pas de "
              "classement des hôpitaux en open data."),
    dict(id="delits_1000hab", label="Délinquance", unit="faits/1000 hab/an", dir=-1, window=3, dec=1,
         theme=T_SECU,
         desc="Violences, vols, cambriolages et dégradations enregistrés par police et "
              "gendarmerie, pour 1 000 habitants et par an (SSMSI, lissé 3 ans). Les communes "
              "touristiques ou commerçantes sont mécaniquement gonflées : les faits y sont "
              "comptés, mais pas les visiteurs dans la population."),
    dict(id="revenu_median", label="Revenu médian (niveau de vie)", unit="€/an", dir=1, window=1, dec=0,
         theme=T_SECU,
         desc="Niveau de vie médian : revenu disponible annuel par « unité de consommation » "
              "(ajusté de la composition du ménage), source FiLoSoFi INSEE 2021. "
              "Médiane France ≈ 23 000 €/an."),
    dict(id="taux_pauvrete", label="Taux de pauvreté", unit="%", dir=-1, window=1, dec=1,
         theme=T_SECU,
         desc="Part des habitants sous le seuil de pauvreté (60 % du niveau de vie médian "
              "national). N'est diffusé que pour ~4 300 communes assez peuplées "
              "(secret statistique) — les autres restent grises."),
    dict(id="maire_politique", label="Orientation politique du maire", unit="-2 gauche → +2 droite", dir=1, window=1, dec=0,
         theme=T_VIE,
         desc="Orientation de la liste arrivée en tête aux municipales de mars 2026, d'après les "
              "nuances du ministère de l'Intérieur : -2 extrême gauche, -1 gauche, 0 centre, "
              "+1 droite, +2 extrême droite. Renseigné pour ~2 700 communes — le ministère "
              "n'attribue de nuance qu'au-dessus de ~3 500 habitants, et les listes « divers » "
              "ne sont pas classables. Le nom et l'étiquette du maire figurent dans la fiche de "
              "chaque commune."),
    dict(id="solde_naturel", label="Solde naturel", unit="‰/an", dir=1, window=3, dec=1,
         theme=T_VIE,
         desc="Naissances moins décès, pour 1 000 habitants et par an. Positif = population "
              "jeune qui se renouvelle (des familles, des écoles qui restent ouvertes) ; "
              "négatif = commune vieillissante."),
    dict(id="dist_arret_tc", label="Distance à un arrêt TC", unit="km", dir=-1, window=1, dec=1,
         theme=T_VIE,
         desc="Distance à vol d'oiseau entre le centre de la commune et l'arrêt de transport en "
              "commun le plus proche (bus, car, tram ou gare — agrégat national des données "
              "GTFS)."),
    dict(id="equip_loisirs_10khab", label="Équipements de loisirs", unit="/10 000 hab", dir=1, window=1, dec=1,
         theme=T_VIE,
         desc="Équipements culturels et sportifs pour 10 000 habitants : cinémas, bibliothèques, "
              "conservatoires, musées, salles de spectacle, piscines, salles de remise en forme "
              "et gymnases (BPE INSEE 2024)."),
]

# métriques de contexte : présentes dans les séries (fiche) mais ni scorées ni dans metrics.json
TREND_YEARS = 5
TREND_CLAMP = 30.0  # %/an


def _percentiles(values: np.ndarray) -> np.ndarray:
    """Rang percentile 0-100 des valeurs non-NaN (NaN → NaN)."""
    out = np.full(values.shape, np.nan)
    mask = ~np.isnan(values)
    n = mask.sum()
    if n > 1:
        out[mask] = (rankdata(values[mask]) - 1) / (n - 1) * 100
    elif n == 1:
        out[mask] = 50
    return out


def build(con, dept: str | None = None) -> None:
    communes = {
        code: {"n": nom, "d": d, "p": pop, "c": [round(lon, 3), round(lat, 3)]}
        for code, nom, d, pop, lon, lat in con.execute(
            "SELECT code_insee, nom, dept, population, lon, lat FROM communes"
        ).fetchall()
    }
    codes = list(communes.keys())
    index = {code: i for i, code in enumerate(codes)}
    n = len(codes)
    n_metrics = len(METRICS)

    levels = np.full((n, n_metrics), np.nan)
    trends = np.full((n, n_metrics), np.nan)

    for j, m in enumerate(METRICS):
        rows = con.execute(
            """
            WITH m AS (SELECT code_insee, annee, valeur FROM metrics WHERE metric = ?),
            maxy AS (SELECT max(annee) AS y FROM m),
            niveau AS (
                SELECT code_insee, avg(valeur) AS v
                FROM m, maxy WHERE annee > y - ? GROUP BY 1
            ),
            tendance AS (
                SELECT code_insee,
                       CASE WHEN count(*) >= 3 AND abs(avg(valeur)) > 1e-9
                            THEN 100 * regr_slope(valeur, annee) / abs(avg(valeur)) END AS t
                FROM m, maxy WHERE annee > y - ? GROUP BY 1
            )
            SELECT code_insee, n.v, t.t
            FROM niveau n LEFT JOIN tendance t USING (code_insee)
            """,
            [m["id"], m["window"], TREND_YEARS],
        ).fetchall()
        for code, v, t in rows:
            i = index.get(code)
            if i is None:
                continue
            levels[i, j] = v
            if t is not None:
                trends[i, j] = max(-TREND_CLAMP, min(TREND_CLAMP, t))
        covered = sum(1 for code, v, t in rows if code in index)
        orphans = len(rows) - covered
        print(f"  [export] {m['id']}: {covered} communes" + (f", {orphans} codes INSEE inconnus" if orphans else ""))

    level_pct = np.apply_along_axis(_percentiles, 0, levels)
    trend_pct = np.apply_along_axis(_percentiles, 0, trends)

    def cell(x: float, dec: int):
        return None if np.isnan(x) else round(float(x), dec) if dec else int(round(float(x)))

    for i, code in enumerate(codes):
        c = communes[code]
        c["v"] = [cell(levels[i, j], METRICS[j]["dec"]) for j in range(n_metrics)]
        c["t"] = [cell(trends[i, j], 1) for j in range(n_metrics)]
        c["vp"] = [cell(level_pct[i, j], 0) for j in range(n_metrics)]
        c["tp"] = [cell(trend_pct[i, j], 0) for j in range(n_metrics)]

    WEB_DATA.mkdir(parents=True, exist_ok=True)
    out = {
        "generated": datetime.date.today().isoformat(),
        "metrics": [
            {"id": m["id"], "label": m["label"], "unit": m["unit"], "dir": m["dir"],
             "dec": m["dec"], "theme": m["theme"], "desc": m["desc"]}
            for m in METRICS
        ],
        "communes": communes,
    }
    path = WEB_DATA / "metrics.json"
    path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(f"  [export] metrics.json ({path.stat().st_size / 1e6:.1f} Mo)")

    # séries annuelles par département (toutes métriques, y compris de contexte)
    decs = {m["id"]: m["dec"] for m in METRICS}
    series_dir = WEB_DATA / "series"
    series_dir.mkdir(exist_ok=True)
    rows = con.execute("""
        SELECT c.dept, m.code_insee, m.metric, m.annee, m.valeur
        FROM metrics m JOIN communes c USING (code_insee)
        ORDER BY c.dept, m.code_insee, m.metric, m.annee
    """).fetchall()
    by_dept: dict[str, dict] = {}
    for d, code, metric, annee, valeur in rows:
        if valeur is None:
            continue
        by_dept.setdefault(d, {}).setdefault(code, {}).setdefault(metric, []).append(
            [int(annee), round(float(valeur), decs.get(metric, 1))]
        )
    for d, data in by_dept.items():
        (series_dir / f"{d}.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print(f"  [export] séries : {len(by_dept)} départements")
