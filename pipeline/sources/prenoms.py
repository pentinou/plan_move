"""Fichier des prénoms INSEE (granularité départementale — il n'existe pas de
version communale) → web/public/data/prenoms.json : top 10 par sexe et par
département pour la dernière année disponible.
"""

from __future__ import annotations

import json
import re

import httpx

from common import DATA, WEB_DATA, download, extract_zip

PAGE = "https://www.insee.fr/fr/statistiques/8595130"
TOP_N = 10


def _resolve() -> str:
    """Adresse du fichier départemental « allégé » le plus récent : l'INSEE remplace
    l'édition précédente sur la même page (prenoms-2024-… puis prenoms-2025-…) et
    l'ancienne adresse renvoie alors une erreur 500."""
    r = httpx.get(PAGE, timeout=60, follow_redirects=True)
    r.raise_for_status()
    noms = re.findall(r"fichier/\d+/prenoms-(\d{4})-dpt-allege_csv\.zip", r.text)
    if not noms:
        raise RuntimeError(f"prénoms : fichier départemental introuvable sur {PAGE}")
    annee = max(noms)
    return f"https://www.insee.fr/fr/statistiques/fichier/8595130/prenoms-{annee}-dpt-allege_csv.zip"


def build(con, dept: str | None = None) -> None:
    zip_path = download(_resolve(), "prenoms/prenoms_dpt.zip")
    out_dir = DATA / "prenoms" / "extrait"
    extract_zip(zip_path, out_dir)
    # un CSV par département : sexe;prenom;periode;dpt;valeur
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE prenoms AS
        SELECT * FROM read_csv('{out_dir}/*.csv', delim = ';', header = true, all_varchar = true)
    """)
    annee_max, = con.execute(
        "SELECT max(TRY_CAST(periode AS INT)) FROM prenoms"
    ).fetchone()
    rows = con.execute(f"""
        SELECT dpt, sexe, prenom, sum(TRY_CAST(valeur AS INT)) AS n
        FROM prenoms
        WHERE TRY_CAST(periode AS INT) = {annee_max} AND prenom NOT LIKE '\\_%' ESCAPE '\\'
        GROUP BY 1, 2, 3
        QUALIFY row_number() OVER (PARTITION BY dpt, sexe ORDER BY n DESC, prenom) <= {TOP_N}
        ORDER BY 1, 2, n DESC, prenom
    """).fetchall()

    out: dict = {"annee": int(annee_max), "depts": {}}
    for d, s, p, n in rows:
        entry = out["depts"].setdefault(d, {"filles": [], "garcons": []})
        entry["filles" if s == "2" else "garcons"].append([p.title(), int(n)])

    WEB_DATA.mkdir(parents=True, exist_ok=True)
    path = WEB_DATA / "prenoms.json"
    path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(f"  [prenoms] top {TOP_N} {annee_max} pour {len(out['depts'])} départements")
