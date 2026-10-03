"""Utilitaires partagés du pipeline Plan Move."""

from __future__ import annotations

import filecmp
import json
import shutil
import zipfile
from pathlib import Path

import duckdb
import httpx

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
TOOLS = ROOT / "tools"
WEB_DATA = ROOT.parent / "web" / "public" / "data"

DB_PATH = DATA / "plan_move.duckdb"


# build.py --refresh : un fichier déjà en cache est revalidé auprès de sa source et
# retéléchargé s'il a changé (sinon le cache est réutilisé sans question).
REFRESH = False
SOURCES_META = DATA / "sources.json"   # validateurs HTTP de chaque fichier téléchargé
CHANGED: list[str] = []                # fichiers (re)téléchargés pendant ce lancement


def _validators(headers) -> dict:
    return {k: headers[k] for k in ("etag", "last-modified", "content-length") if headers.get(k)}


def _meta() -> dict:
    try:
        return json.loads(SOURCES_META.read_text())
    except (OSError, ValueError):
        return {}


def _changed_upstream(url: str, dest: Path, known: dict | None) -> bool | None:
    """La source a-t-elle changé depuis notre téléchargement ? On n'en lit que les
    en-têtes (GET coupé aussitôt : certains serveurs refusent HEAD). Sans validateur
    commun, on compare la taille annoncée à celle du fichier ; à défaut, on considère
    que la source a changé (mieux vaut retélécharger qu'ignorer une mise à jour)."""
    with httpx.stream("GET", url, follow_redirects=True, timeout=120) as r:
        r.raise_for_status()
        now = _validators(r.headers)
    known = known or {"content-length": str(dest.stat().st_size)}
    for k in ("etag", "last-modified", "content-length"):
        if k in now and k in known:
            return now[k] != known[k]
    return None   # impossible à dire sans retélécharger


def download(url: str, dest_name: str, *, force: bool = False) -> Path:
    """Télécharge `url` vers data/<dest_name>, avec cache (ne retélécharge pas si présent,
    sauf avec REFRESH quand la source a changé)."""
    dest = DATA / dest_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    meta = _meta()
    if dest.exists() and not force:
        if not REFRESH:
            return dest
        change = _changed_upstream(url, dest, meta.get(dest_name))
        if change is False:
            return dest
        print(f"  ↻ {dest_name} : " + ("a changé à la source, nouveau téléchargement" if change
                                      else "la source ne dit pas si elle a changé, téléchargement pour comparer"))
    tmp = dest.with_name(dest.name + ".part")
    with httpx.stream("GET", url, follow_redirects=True, timeout=300) as r:
        r.raise_for_status()
        meta[dest_name] = {"url": url, **_validators(r.headers)}
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:  # % borné : total = taille compressée si le serveur gzippe
                    print(f"\r  ↓ {dest_name}  {min(100, 100 * done // total):3d} % "
                          f"({done / 1e6:.1f}/{total / 1e6:.1f} Mo)", end="", flush=True)
                else:  # taille inconnue (certains exports d'API) : juste le volume reçu
                    print(f"\r  ↓ {dest_name}  {done / 1e6:.1f} Mo", end="", flush=True)
    SOURCES_META.write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    # sources sans validateur HTTP (exports d'API) : retéléchargées à chaque --refresh,
    # mais signalées comme changées seulement si leur contenu diffère vraiment
    if dest.exists() and filecmp.cmp(tmp, dest, shallow=False):
        tmp.unlink()
        print(f"\r  {dest_name} : inchangé".ljust(76))
        return dest
    tmp.replace(dest)
    CHANGED.append(dest_name)
    print(f"\r  téléchargé {dest_name} ({dest.stat().st_size / 1e6:.1f} Mo)".ljust(76))
    return dest


def stale(derived: Path, source: Path) -> bool:
    """Un fichier ou dossier dérivé (archive décompressée, conversion) est à refaire s'il
    manque ou s'il est plus ancien que sa source, par exemple retéléchargée par --refresh."""
    return not derived.exists() or derived.stat().st_mtime < source.stat().st_mtime


def extract_zip(zip_path: Path, out_dir: Path) -> None:
    """Décompresse zip_path dans out_dir, sauf si l'extraction est déjà à jour."""
    if stale(out_dir, zip_path):
        shutil.rmtree(out_dir, ignore_errors=True)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(out_dir)


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
