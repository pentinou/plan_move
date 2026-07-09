"""Orientation politique du maire (municipales 2026, ministère de l'Intérieur + RNE) :
- maire_politique : position de la liste arrivée en tête au tour décisif sur un axe
  gauche-droite (-2 extrême gauche, -1 gauche, 0 centre, +1 droite, +2 extrême droite),
  d'après la nuance attribuée par le ministère de l'Intérieur. Les nuances ne sont
  attribuées qu'aux communes d'environ 3 500 hab et plus (~3 300 communes) ; LDIV et
  LREG sont inclassables sur cet axe → pas de valeur.
- web/public/data/maires/{dept}.json : par commune [nom du maire (RNE), libellé nuance]
"""

from __future__ import annotations

import csv
import json

from common import WEB_DATA, datagouv_resources, download, replace_source

RNE = "repertoire-national-des-elus-1"
T1 = "elections-municipales-2026-resultats-du-premier-tour"
T2 = "elections-municipales-2026-resultats-du-second-tour"
ANNEE = 2026

# Position sur l'axe gauche-droite (regroupements du référentiel du ministère) ;
# None = nuance sans position (divers, régionaliste).
AXE: dict[str, int | None] = {
    "LEXG": -2,
    "LFI": -1, "LCOM": -1, "LSOC": -1, "LVEC": -1, "LUG": -1, "LDVG": -1,
    "LECO": 0, "LREN": 0, "LMDM": 0, "LHOR": 0, "LUDI": 0, "LUC": 0, "LDVC": 0,
    "LDIV": None, "LREG": None,
    "LLR": 1, "LUD": 1, "LDVD": 1, "LDSV": 1, "LUDR": 1,
    "LRN": 2, "LREC": 2, "LUXD": 2, "LEXD": 2,
}

LIBELLES = {
    "LEXG": "Extrême gauche", "LFI": "La France insoumise", "LCOM": "Communiste",
    "LSOC": "Socialiste", "LVEC": "Écologiste", "LUG": "Union de la gauche",
    "LDVG": "Divers gauche", "LECO": "Écologiste (divers)", "LREG": "Régionaliste",
    "LDIV": "Divers", "LREN": "Renaissance", "LMDM": "MoDem", "LHOR": "Horizons",
    "LUDI": "UDI", "LUC": "Union du centre", "LDVC": "Divers centre",
    "LLR": "Les Républicains", "LUD": "Union de la droite", "LDVD": "Divers droite",
    "LDSV": "Droite souverainiste", "LUDR": "Union des droites pour la République",
    "LRN": "Rassemblement national", "LREC": "Reconquête",
    "LUXD": "Union d'extrême droite", "LEXD": "Extrême droite",
}


def _resolve(dataset: str, title_prefix: str) -> str:
    for r in datagouv_resources(dataset):
        if r["title"].startswith(title_prefix):
            return r["url"]
    raise RuntimeError(f"ressource « {title_prefix}… » introuvable dans {dataset}")


def _int(s: str) -> int | None:
    try:
        return int(s.strip())
    except (ValueError, AttributeError):
        return None


def _gagnantes(path) -> dict[str, str]:
    """Code INSEE → nuance de la liste en tête (max sièges au CM, puis voix).
    Les colonnes des listes se répètent par blocs de 13 à partir de la colonne 18
    (nuance = +4, voix = +7, sièges CM = +11)."""
    out: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        rows = csv.reader(f, delimiter=";")
        next(rows)
        for row in rows:
            code = row[2].strip().zfill(5)
            best: tuple[int, int, str] | None = None
            for k in range(18, len(row) - 12, 13):
                voix, sieges = _int(row[k + 7]), _int(row[k + 11])
                if voix is None and sieges is None:
                    continue
                cand = (sieges or 0, voix or 0, row[k + 4].strip())
                if best is None or cand[:2] > best[:2]:
                    best = cand
            if best:
                out[code] = best[2]
    return out


def _maires(path) -> dict[str, str]:
    """Code INSEE → « Prénom Nom » du maire (RNE, fichier elus-maires)."""
    out: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        rows = csv.reader(f, delimiter=";")
        next(rows)
        for row in rows:
            code = row[4].strip().zfill(5)
            out[code] = f"{row[7].strip()} {row[6].strip()}".strip()
    return out


def build(con, dept: str | None = None) -> None:
    rne = download(_resolve(RNE, "elus-maires"), "maires/rne_maires.csv")
    t1 = download(_resolve(T1, "Municipales 2026 - Résultats - Communes"),
                  "maires/resultats_communes_t1.csv")
    t2 = download(_resolve(T2, "Municipales 2026 - Résultats - Communes"),
                  "maires/resultats_communes_t2.csv")

    nuances = _gagnantes(t1)
    nuances.update(_gagnantes(t2))  # le second tour remplace le premier
    maires = _maires(rne)

    con.execute("""
        CREATE OR REPLACE TEMP TABLE maires_out (
            code_insee VARCHAR, annee SMALLINT, metric VARCHAR, valeur DOUBLE
        )
    """)
    con.executemany(
        "INSERT INTO maires_out VALUES (?, ?, 'maire_politique', ?)",
        [
            (code, ANNEE, AXE[n])
            for code, n in nuances.items()
            if AXE.get(n) is not None and (not dept or code.startswith(dept))
        ],
    )
    avec_nuance = sum(1 for n in nuances.values() if n)
    sans_axe = sum(1 for n in nuances.values() if n and AXE.get(n) is None)
    print(f"  [maires] {avec_nuance}/{len(nuances)} communes avec nuance ministère, "
          f"dont {sans_axe} inclassables (div/reg)")
    replace_source(con, "maires", "SELECT * FROM maires_out")

    # fiche : maire + nuance par commune, un fichier par département (France entière)
    by_dept: dict[str, dict] = {}
    for code, nom in maires.items():
        d = code[:3] if code.startswith("97") else code[:2]
        lib = LIBELLES.get(nuances.get(code, ""), "")
        by_dept.setdefault(d, {})[code] = [nom, lib]
    out_dir = WEB_DATA / "maires"
    out_dir.mkdir(parents=True, exist_ok=True)
    for d, data in by_dept.items():
        (out_dir / f"{d}.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print(f"  [maires] fiches maires : {len(maires)} communes, {len(by_dept)} départements")
