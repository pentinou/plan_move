#!/usr/bin/env bash
# Installe et prépare Plan Move (Linux / macOS / WSL).
#
# Usage :
#   ./install.sh                 installe tout + génère les données (France entière, long)
#   ./install.sh --dept 44       génère les données d'un seul département (rapide)
#   ./install.sh --skip-build    installe les dépendances sans générer les données
set -euo pipefail
cd "$(dirname "$0")"

info() { printf '\033[1;34m▶ %s\033[0m\n' "$*"; }
err()  { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; }

# --- options ---
DEPT=""
SKIP_BUILD=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dept) DEPT="${2:?--dept requiert un code département}"; shift 2;;
    --skip-build) SKIP_BUILD=1; shift;;
    -h|--help) sed -n '2,7p' "$0"; exit 0;;
    *) err "option inconnue : $1"; exit 1;;
  esac
done

# --- prérequis ---
need() { command -v "$1" >/dev/null 2>&1 || { err "$1 introuvable — $2"; exit 1; }; }
need uv   "installez-le : https://docs.astral.sh/uv/"
need node "installez Node.js ≥ 18 : https://nodejs.org/"
need npm  "fourni avec Node.js"
if ! command -v tippecanoe >/dev/null 2>&1 && [ ! -x pipeline/tools/tippecanoe ]; then
  err "tippecanoe introuvable (ni dans le PATH, ni dans pipeline/tools/)."
  err "  macOS : brew install tippecanoe"
  err "  Linux : sudo apt install tippecanoe   (ou compilez github.com/felt/tippecanoe)"
  exit 1
fi

# --- 1. dépendances + données du pipeline ---
info "Dépendances Python (uv sync)…"
( cd pipeline && uv sync )

if [ "$SKIP_BUILD" -eq 0 ]; then
  if [ -n "$DEPT" ]; then
    info "Génération des données pour le département $DEPT…"
    ( cd pipeline && uv run build.py --dept "$DEPT" )
  else
    info "Génération des données (France entière — ~15 min au premier lancement)…"
    ( cd pipeline && uv run build.py )
  fi
else
  info "Génération des données ignorée (--skip-build)."
fi

# --- 2. dépendances web ---
info "Dépendances web (npm install)…"
( cd web && npm install )

echo
info "Installation terminée."
echo
echo "  Pour lancer la carte :"
echo "      cd web"
echo "      npm run dev"
echo
echo "  puis ouvrir http://localhost:5173 dans le navigateur."
echo "  (Ctrl+C dans le terminal pour arrêter le serveur.)"
if [ "$SKIP_BUILD" -eq 1 ]; then
  echo
  echo "  ⚠ Données non générées (--skip-build) : lancez d'abord 'cd pipeline && uv run build.py'."
fi
