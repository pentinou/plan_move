#!/bin/bash
# Mise à jour mensuelle de Plan Move (lancée par planmove-update.timer, ou à la main :
# sudo systemctl start planmove-update). Revalide les sources, recalcule, contrôle, puis
# publie le site — ou garde la version en ligne si un contrôle échoue. Compte rendu par mail.
set -uo pipefail

PY="$DATA_DIR/venv/bin/python"
SITE="$DATA_DIR/site"
JOURNAL="$DATA_DIR/derniere-maj.log"
debut=$(date +%s)
: > "$JOURNAL"

compte_rendu() {   # $1 = sujet ; le corps est lu sur l'entrée standard
    local corps
    corps=$(cat)
    printf '%s\n' "$corps"
    [ -n "${REPORT_EMAIL:-}" ] && printf '%s\n\nDurée : %s min. Journal complet : %s\n' \
        "$corps" "$(( ($(date +%s) - debut) / 60 ))" "$JOURNAL" | mail -s "$1" "$REPORT_EMAIL"
}

echo "== $(date '+%F %T') : mise à jour de Plan Move"
cd "$INSTALL_DIR/pipeline" || exit 1

if ! "$PY" build.py --refresh >> "$JOURNAL" 2>&1; then
    tail -30 "$JOURNAL" | compte_rendu "Plan Move : ÉCHEC du calcul, version en ligne conservée"
    exit 1
fi

if ! "$PY" check.py --previous "$SITE/data/metrics.json" --json "$DATA_DIR/controle.json" >> "$JOURNAL" 2>&1; then
    { echo "Le contrôle a refusé les nouvelles données :"; grep -E "ERREUR|AVERTISSEMENT" "$JOURNAL"; } \
        | compte_rendu "Plan Move : contrôle en ÉCHEC, version en ligne conservée"
    exit 1
fi

cd "$INSTALL_DIR/web" || exit 1
if ! { npm ci --no-audit --no-fund --loglevel=error && npm run build; } >> "$JOURNAL" 2>&1; then
    tail -30 "$JOURNAL" | compte_rendu "Plan Move : ÉCHEC de la construction du site, version en ligne conservée"
    exit 1
fi

# publication : copie à côté puis échange des dossiers (le site n'est jamais à moitié copié)
rsync -a --delete dist/ "$SITE.nouveau/"
[ -d "$SITE" ] && mv "$SITE" "$SITE.ancien"
mv "$SITE.nouveau" "$SITE"
rm -rf "$SITE.ancien"

{
    echo "Nouvelle version publiée."
    echo
    python3 - "$DATA_DIR/pipeline-data/refresh.json" "$DATA_DIR/controle.json" <<'PYEOF'
import json, sys
r = json.load(open(sys.argv[1])); c = json.load(open(sys.argv[2]))
print("Sources mises à jour :", ", ".join(r["changed"]) if r["changed"] else "aucune (données inchangées)")
for x in c["infos"]: print(x)
for x in c["avertissements"]: print("À FAIRE :", x)
PYEOF
} | compte_rendu "Plan Move : données à jour"
