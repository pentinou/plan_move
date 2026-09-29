#!/usr/bin/env bash
# Prépare et lance Plan Move (Linux / macOS / WSL), sans droits root.
#
# Usage :
#   ./start.sh                 vérifie/installe les outils, génère les données si absentes, lance la carte
#   ./start.sh --dept 44       génère les données d'un seul département (rapide) si elles manquent
#   ./start.sh --rebuild       régénère les données même si elles existent déjà
#   ./start.sh --update        met aussi à jour uv et les librairies Python/JS (modifie uv.lock / package-lock.json)
#   ./start.sh --no-serve      prépare tout sans lancer le serveur
#
# Outils installés au besoin dans pipeline/tools/ (non versionné) : Node.js, tippecanoe.
# uv est installé par son script officiel dans ~/.local/bin.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$PWD"
TOOLS="$ROOT/pipeline/tools"
WEB_DATA="$ROOT/web/public/data"

info() { printf '\033[1;34m▶ %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m✓ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m⚠ %s\033[0m\n' "$*"; }
err()  { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; }

# --- options ---
DEPT=""
REBUILD=0
UPDATE=0
SERVE=1
while [ $# -gt 0 ]; do
  case "$1" in
    --dept) DEPT="${2:?--dept requiert un code département}"; shift 2;;
    --rebuild) REBUILD=1; shift;;
    --update) UPDATE=1; shift;;
    --no-serve) SERVE=0; shift;;
    -h|--help) sed -n '2,12p' "$0"; exit 0;;
    *) err "option inconnue : $1"; exit 1;;
  esac
done

# vrai si la version $1 >= $2
ver_ge() { [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -1)" = "$2" ]; }

OS="$(uname -s)"
case "$(uname -m)" in
  x86_64|amd64) ARCH=x64;;
  aarch64|arm64) ARCH=arm64;;
  *) ARCH="$(uname -m)";;
esac

need() { command -v "$1" >/dev/null 2>&1 || { err "$1 introuvable — $2"; exit 1; }; }
need curl "installez curl (sudo apt install curl)"
need tar  "installez tar"

mkdir -p "$TOOLS"
export PATH="$TOOLS/node/bin:$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

# --- 1. uv (Python + dépendances du pipeline) ---
if ! command -v uv >/dev/null 2>&1; then
  info "Installation de uv…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
if [ "$UPDATE" -eq 1 ]; then
  info "Mise à jour de uv…"
  uv self update || warn "uv self update impossible (uv installé par un gestionnaire de paquets ?) — on continue."
fi
ok "uv $(uv --version | awk '{print $2}')"

# --- 2. Node.js (Vite 8 exige ^20.19 ou >= 22.12) ---
node_ok() {
  command -v node >/dev/null 2>&1 || return 1
  local v; v="$(node --version | sed 's/^v//')"
  if [ "${v%%.*}" -eq 20 ]; then ver_ge "$v" 20.19.0; else ver_ge "$v" 22.12.0; fi
}
if ! node_ok; then
  [ -n "$(command -v node || true)" ] && warn "Node $(node --version) trop ancien pour Vite 8."
  info "Installation de Node.js LTS dans pipeline/tools/node…"
  case "$OS" in
    Linux) NODE_OS=linux;;
    Darwin) NODE_OS=darwin;;
    *) err "système non géré pour l'installation de Node : $OS"; exit 1;;
  esac
  NODE_TGZ="$(curl -fsSL https://nodejs.org/dist/latest-v22.x/SHASUMS256.txt \
    | awk '{print $2}' | grep -E "^node-v[0-9.]+-$NODE_OS-$ARCH\.tar\.gz$" | head -1)"
  [ -n "$NODE_TGZ" ] || { err "archive Node introuvable pour $NODE_OS-$ARCH"; exit 1; }
  rm -rf "$TOOLS/node" && mkdir -p "$TOOLS/node"
  curl -fsSL "https://nodejs.org/dist/latest-v22.x/$NODE_TGZ" | tar -xz -C "$TOOLS/node" --strip-components=1
  hash -r
fi
ok "node $(node --version), npm $(npm --version)"

# --- 3. tippecanoe (>= 2.17 : première version qui écrit du PMTiles) ---
tippecanoe_cmd() {
  if [ -x "$TOOLS/tippecanoe" ]; then echo "$TOOLS/tippecanoe"; else command -v tippecanoe || true; fi
}
tippecanoe_ok() {
  local bin; bin="$(tippecanoe_cmd)"
  [ -n "$bin" ] || return 1
  ver_ge "$("$bin" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)" 2.17.0
}
install_tippecanoe() {
  # a) Debian/Ubuntu : paquet .deb extrait sans sudo
  if command -v apt-get >/dev/null 2>&1 && command -v dpkg-deb >/dev/null 2>&1; then
    local tmp; tmp="$(mktemp -d)"
    if ( cd "$tmp" && apt-get download tippecanoe >/dev/null 2>&1 ); then
      dpkg-deb -x "$tmp"/tippecanoe_*.deb "$tmp/x"
      cp "$tmp"/x/usr/bin/tippecanoe* "$tmp"/x/usr/bin/tile-join "$TOOLS/"
      rm -rf "$tmp"
      tippecanoe_ok && return 0
      warn "le paquet apt est trop ancien, compilation depuis les sources…"
    fi
    rm -rf "$tmp"
  fi
  # b) macOS : Homebrew
  if [ "$OS" = Darwin ] && command -v brew >/dev/null 2>&1; then
    brew install tippecanoe && return 0
  fi
  # c) compilation depuis les sources (felt/tippecanoe)
  need make "installez les outils de compilation (sudo apt install build-essential)"
  need g++  "installez les outils de compilation (sudo apt install build-essential)"
  local src; src="$(mktemp -d)"
  git clone --depth 1 https://github.com/felt/tippecanoe "$src/tippecanoe"
  # sqlite3.h absent sans le paquet -dev : on compile l'amalgamation SQLite à côté
  if ! printf '#include <sqlite3.h>\n' | cc -E - >/dev/null 2>&1; then
    local zip; zip="$(curl -fsSL https://www.sqlite.org/download.html \
      | grep -oE '[0-9]{4}/sqlite-amalgamation-[0-9]+\.zip' | head -1)"
    curl -fsSL "https://www.sqlite.org/$zip" -o "$src/sqlite.zip"
    ( cd "$src" && uv run --no-project python -m zipfile -e sqlite.zip . )
    local dir; dir="$(ls -d "$src"/sqlite-amalgamation-*)"
    ( cd "$dir" && cc -O2 -c sqlite3.c -o sqlite3.o && ar rcs libsqlite3.a sqlite3.o )
    export CPATH="$dir${CPATH:+:$CPATH}" LIBRARY_PATH="$dir${LIBRARY_PATH:+:$LIBRARY_PATH}"
  fi
  ( cd "$src/tippecanoe" && make -j"$(nproc 2>/dev/null || echo 2)" )
  cp "$src"/tippecanoe/{tippecanoe,tile-join,tippecanoe-decode} "$TOOLS/"
  rm -rf "$src"
}
if ! tippecanoe_ok; then
  [ -n "$(tippecanoe_cmd)" ] && warn "$("$(tippecanoe_cmd)" --version 2>&1 | head -1) trop ancien (PMTiles requis)."
  info "Installation de tippecanoe dans pipeline/tools…"
  install_tippecanoe
  tippecanoe_ok || { err "tippecanoe n'a pas pu être installé."; exit 1; }
fi
ok "$("$(tippecanoe_cmd)" --version 2>&1 | head -1)"

# --- 4. librairies Python et JS ---
if [ "$UPDATE" -eq 1 ]; then
  info "Mise à jour des librairies Python (uv lock --upgrade)…"
  ( cd pipeline && uv lock --upgrade )
fi
info "Librairies Python (uv sync)…"
( cd pipeline && uv sync --quiet )
if [ "$UPDATE" -eq 1 ]; then
  info "Mise à jour des librairies JS (npm update)…"
  ( cd web && npm update --no-audit --no-fund )
fi
info "Librairies JS (npm install)…"
( cd web && npm install --no-audit --no-fund --loglevel=error )

# --- 5. données ---
# Vérifie que les données produiront une carte colorée : tuiles PMTiles valides
# et au moins une commune avec un centile (sinon tout reste gris).
data_ok() {
  [ -f "$WEB_DATA/metrics.json" ] && [ -f "$WEB_DATA/communes.pmtiles" ] || return 1
  [ "$(head -c 7 "$WEB_DATA/communes.pmtiles")" = "PMTiles" ] || { warn "communes.pmtiles n'est pas au format PMTiles."; return 1; }
  node -e '
    const ds = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"));
    const n = Object.values(ds.communes).filter((c) => (c.vp || []).some((p) => p !== null)).length;
    console.log(`  ${n} communes notées sur ${Object.keys(ds.communes).length}`);
    process.exit(n > 0 ? 0 : 1);
  ' "$WEB_DATA/metrics.json" || { warn "metrics.json ne contient aucune commune notée."; return 1; }
}
if [ "$REBUILD" -eq 1 ] || ! data_ok; then
  if [ -n "$DEPT" ]; then
    info "Génération des données pour le département $DEPT…"
    ( cd pipeline && uv run build.py --dept "$DEPT" )
  else
    info "Génération des données (France entière — ~15 min au premier lancement)…"
    ( cd pipeline && uv run build.py )
  fi
  data_ok || { err "Les données générées sont inutilisables (voir messages ci-dessus)."; exit 1; }
fi
ok "Données prêtes (générées le $(grep -oE '"generated":"[^"]+"' "$WEB_DATA/metrics.json" | cut -d'"' -f4))"

# --- 6. lancement ---
if [ "$SERVE" -eq 0 ]; then
  ok "Prêt. Lancez la carte avec : cd web && npm run dev"
  exit 0
fi
info "Lancement de la carte sur http://localhost:5173 (Ctrl+C pour arrêter)…"
cd web
exec npm run dev
