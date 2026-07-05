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

METRICS = [
    dict(id="prix_maison_m2", label="Prix des maisons", unit="€/m²", dir=-1, window=3, dec=0),
    dict(id="prix_terrain_m2", label="Prix des terrains à bâtir", unit="€/m²", dir=-1, window=3, dec=0),
    dict(id="loyer_maison_m2", label="Loyer des maisons", unit="€/m²/mois", dir=-1, window=1, dec=1),
    dict(id="loyer_appart_m2", label="Loyer des appartements", unit="€/m²/mois", dir=-1, window=1, dec=1),
    dict(id="ventes_1000hab", label="Marché immobilier", unit="ventes/1000 hab/an", dir=1, window=3, dec=1),
    dict(id="taxe_fonciere", label="Taxe foncière (taux communal)", unit="%", dir=-1, window=1, dec=1),
    dict(id="delits_1000hab", label="Délinquance", unit="faits/1000 hab/an", dir=-1, window=3, dec=1),
    dict(id="revenu_median", label="Revenu médian (niveau de vie)", unit="€/an", dir=1, window=1, dec=0),
    dict(id="taux_pauvrete", label="Taux de pauvreté", unit="%", dir=-1, window=1, dec=1),
    dict(id="solde_naturel", label="Solde naturel", unit="‰/an", dir=1, window=3, dec=1),
    dict(id="nb_ecoles", label="Écoles à ≤10 km", unit="écoles", dir=1, window=1, dec=0),
    dict(id="ips_ecoles", label="IPS des écoles", unit="indice", dir=1, window=1, dec=0),
    dict(id="reussite_dnb", label="Réussite au brevet", unit="%", dir=1, window=3, dec=1),
    dict(id="reussite_bac", label="Réussite au bac", unit="%", dir=1, window=3, dec=1),
    dict(id="va_college", label="Valeur ajoutée du collège", unit="pts", dir=1, window=3, dec=1),
    dict(id="dist_arret_tc", label="Distance à un arrêt TC", unit="km", dir=-1, window=1, dec=1),
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
            {"id": m["id"], "label": m["label"], "unit": m["unit"], "dir": m["dir"], "dec": m["dec"]}
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
