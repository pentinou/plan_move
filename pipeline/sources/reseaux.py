"""Réseau routier principal et voies ferrées (IGN ROUTE 500, Licence Ouverte)
→ web/public/data/reseaux.pmtiles (couches `routes` et `fer`).

Couches d'habillage de la carte, indépendantes de la table metrics.
Routes retenues : type autoroutier, liaisons principales et régionales
(les liaisons locales noieraient la choroplèthe).
"""

from __future__ import annotations

import json
import subprocess

import py7zr
import shapefile
from pyproj import Transformer

from common import DATA, TOOLS, WEB_DATA, download

URL = (
    "https://data.geopf.fr/telechargement/download/ROUTE500/"
    "ROUTE500_3-0__SHP_LAMB93_FXX_2021-11-03/ROUTE500_3-0__SHP_LAMB93_FXX_2021-11-03.7z"
)
VOCATIONS = {
    "Type autoroutier": "autoroute",
    "Liaison principale": "principale",
    "Liaison régionale": "principale",
}

_transformer = Transformer.from_crs(2154, 4326, always_xy=True)


def _to_ndjson(shp_path, ndjson_path, props_fn) -> int:
    """Shapefile Lambert-93 → GeoJSON par ligne (WGS84). Une feature par partie de
    polyligne ; props_fn(record) renvoie les propriétés ou None pour ignorer."""
    n = 0
    with shapefile.Reader(str(shp_path), encoding="latin-1") as rd, open(ndjson_path, "w") as out:
        for sr in rd.iterShapeRecords():
            props = props_fn(sr.record)
            if props is None:
                continue
            pts = sr.shape.points
            parts = list(sr.shape.parts) + [len(pts)]
            for i in range(len(parts) - 1):
                seg = pts[parts[i] : parts[i + 1]]
                if len(seg) < 2:
                    continue
                lons, lats = _transformer.transform([p[0] for p in seg], [p[1] for p in seg])
                coords = [[round(x, 5), round(y, 5)] for x, y in zip(lons, lats)]
                out.write(json.dumps({
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": coords},
                    "properties": props,
                }, separators=(",", ":")) + "\n")
                n += 1
    return n


def build(con, dept: str | None = None) -> None:
    archive = download(URL, "reseaux/route500.7z")
    shp_dir = DATA / "reseaux" / "shp"
    if not shp_dir.exists():
        with py7zr.SevenZipFile(archive) as z:
            targets = [n for n in z.getnames()
                       if "TRONCON_ROUTE" in n or "TRONCON_VOIE_FERREE" in n]
            z.extract(path=shp_dir, targets=targets)
        print(f"  [reseaux] {len(targets)} fichiers extraits de l'archive")

    routes_shp = next(shp_dir.rglob("TRONCON_ROUTE.shp"))
    fer_shp = next(shp_dir.rglob("TRONCON_VOIE_FERREE.shp"))

    routes_nd = DATA / "reseaux" / "routes.ndjson"
    fer_nd = DATA / "reseaux" / "fer.ndjson"

    def route_props(rec):
        classe = VOCATIONS.get(getattr(rec, "VOCATION", None))
        return {"classe": classe} if classe else None

    def fer_props(rec):
        etat = getattr(rec, "ETAT", "En service") or "En service"
        if not etat.startswith("En service"):
            return None
        return {}

    n_routes = _to_ndjson(routes_shp, routes_nd, route_props)
    n_fer = _to_ndjson(fer_shp, fer_nd, fer_props)
    print(f"  [reseaux] {n_routes} tronçons routiers, {n_fer} tronçons ferrés")

    out = WEB_DATA / "reseaux.pmtiles"
    subprocess.run(
        [
            str(TOOLS / "tippecanoe"),
            "-o", str(out),
            "--minimum-zoom=4",
            "--maximum-zoom=11",
            "--drop-densest-as-needed",
            "--quiet",
            "--force",
            "-L", f"routes:{routes_nd}",
            "-L", f"fer:{fer_nd}",
        ],
        check=True,
    )
    print(f"  [reseaux] {out.name} généré ({out.stat().st_size / 1e6:.1f} Mo)")
