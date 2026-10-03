#!/bin/bash

REPO="https://github.com/pentinou/plan_move.git"   # dépôt public : pas de clé de déploiement
BRANCH="yunohost"
TIPPECANOE_TAG="2.79.0"

# Code depuis GitHub. Le cache des téléchargements (~3 Go), les outils et le site publié
# vivent dans $data_dir : ils survivent aux mises à jour du code.
_pm_setup_code() {
    export HOME="${HOME:-/root}"     # les scripts YunoHost tournent sans $HOME
    if [ -d "$install_dir/.git" ]; then
        git -c safe.directory="$install_dir" -C "$install_dir" fetch --quiet origin "$BRANCH"
        git -c safe.directory="$install_dir" -C "$install_dir" reset --quiet --hard "origin/$BRANCH"
    else
        git clone --quiet --branch "$BRANCH" "$REPO" "$install_dir.clone"
        cp -a "$install_dir.clone/." "$install_dir/"
        ynh_safe_rm "$install_dir.clone"
    fi
    mkdir -p "$data_dir/pipeline-data" "$data_dir/tools" "$data_dir/site"
    ln -sfn "$data_dir/pipeline-data" "$install_dir/pipeline/data"
    ln -sfn "$data_dir/tools" "$install_dir/pipeline/tools"
    chown -R "$app:$app" "$install_dir"
}

# uv + Python 3.12 + dépendances du pipeline, et tippecanoe compilé.
_pm_setup_tools() {
    local tools="$data_dir/tools"
    export UV_CACHE_DIR="$data_dir/uv-cache" UV_PYTHON_INSTALL_DIR="$data_dir/uv-python"
    if [ ! -x "$tools/uv" ]; then
        curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$tools" INSTALLER_NO_MODIFY_PATH=1 sh >/dev/null
    fi
    "$tools/uv" venv --quiet --allow-existing --python 3.12 "$data_dir/venv"
    # numpy < 2.3 : ce serveur a un Core 2 (ni SSE4.2 ni POPCNT) ; numpy >= 2.3 exige
    # x86-64-v2 et refuse de s'importer (vérifié le 2026-10-03 ; scipy, duckdb, pyproj OK).
    "$tools/uv" pip install --quiet --python "$data_dir/venv/bin/python" \
        -r "$install_dir/pipeline/pyproject.toml" "numpy<2.3"
    if [ ! -x "$tools/tippecanoe" ] || ! "$tools/tippecanoe" --version 2>&1 | grep -q "$TIPPECANOE_TAG"; then
        local src
        src=$(mktemp -d)
        git clone --quiet --depth 1 --branch "$TIPPECANOE_TAG" https://github.com/felt/tippecanoe "$src/t"
        ynh_hide_warnings make -C "$src/t" -j"$(nproc)" tippecanoe
        cp "$src/t/tippecanoe" "$tools/"
        ynh_safe_rm "$src"
    fi
    chown -R "$app:$app" "$data_dir"
    # nginx (www-data) doit pouvoir traverser $data_dir pour servir site/ :
    # le chown ci-dessus retire le groupe posé par la ressource data_dir
    chgrp www-data "$data_dir"
    chmod 750 "$data_dir"
}

_pm_setup_systemd() {
    mkdir -p "/var/log/$app"
    chown -R "$app:$app" "/var/log/$app"
    ynh_config_add_logrotate
    ynh_config_add_systemd --service="$app-update" --template="update.service"
    ynh_config_add --template="update.timer" --destination="/etc/systemd/system/$app-update.timer"
    systemctl daemon-reload
    systemctl enable --quiet "$app-update.timer"
    systemctl start "$app-update.timer"
}
