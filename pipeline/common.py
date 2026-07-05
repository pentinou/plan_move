"""Utilitaires partagés du pipeline Plan Move."""

from __future__ import annotations

from pathlib import Path

import duckdb
import httpx

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
TOOLS = ROOT / "tools"
WEB_DATA = ROOT.parent / "web" / "public" / "data"

DB_PATH = DATA / "plan_move.duckdb"


def download(url: str, dest_name: str, *, force: bool = False) -> Path:
    """Télécharge `url` vers data/<dest_name>, avec cache (ne retélécharge pas si présent)."""
    dest = DATA / dest_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        return dest
    tmp = dest.with_name(dest.name + ".part")
    with httpx.stream("GET", url, follow_redirects=True, timeout=300) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
    tmp.rename(dest)
    print(f"  téléchargé {dest_name} ({dest.stat().st_size / 1e6:.1f} Mo)")
    return dest


def datagouv_resources(dataset_slug: str) -> list[dict]:
    """Ressources d'un jeu de données data.gouv.fr (pour résoudre les URLs à jour)."""
    r = httpx.get(
        f"https://www.data.gouv.fr/api/1/datasets/{dataset_slug}/",
        timeout=60,
        follow_redirects=True,
    )
    r.raise_for_status()
    return r.json()["resources"]


def tippecanoe_bin() -> str:
    """Chemin du binaire tippecanoe : celui compilé dans pipeline/tools/ s'il existe,
    sinon celui du PATH (installé via brew/apt). Voir README § Prérequis."""
    local = TOOLS / "tippecanoe"
    return str(local) if local.exists() else "tippecanoe"


def remap_plm(col: str) -> str:
    """Expression SQL ramenant les codes d'arrondissement de Paris/Lyon/Marseille
    au code de la commune entière (les contours et l'API Géo ignorent les arrondissements)."""
    return (
        f"CASE WHEN {col} BETWEEN '75101' AND '75120' THEN '75056' "
        f"WHEN {col} BETWEEN '13201' AND '13216' THEN '13055' "
        f"WHEN {col} BETWEEN '69381' AND '69389' THEN '69123' ELSE {col} END"
    )


def connect() -> duckdb.DuckDBPyConnection:
    DATA.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS metrics (
            source     VARCHAR NOT NULL,
            code_insee VARCHAR NOT NULL,
            annee      SMALLINT NOT NULL,
            metric     VARCHAR NOT NULL,
            valeur     DOUBLE
        )
    """)
    return con


def replace_source(con: duckdb.DuckDBPyConnection, source: str, select_sql: str) -> None:
    """Remplace les lignes d'une source dans `metrics` par le résultat d'un SELECT
    (code_insee, annee, metric, valeur)."""
    con.execute("DELETE FROM metrics WHERE source = ?", [source])
    con.execute(f"INSERT INTO metrics SELECT '{source}', * FROM ({select_sql})")
    n, communes = con.execute(
        "SELECT count(*), count(DISTINCT code_insee) FROM metrics WHERE source = ?", [source]
    ).fetchone()
    print(f"  [{source}] {n} lignes, {communes} communes")
