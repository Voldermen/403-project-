#!/usr/bin/env bash
# Clones a GitHub repo, installs requirements, runs the app, and
# periodically pulls updates (reinstalling deps and restarting on change).
set -euo pipefail

: "${REPO_URL:?Set REPO_URL, e.g. https://github.com/you/yourrepo.git}"
: "${START_CMD:?Set START_CMD, e.g. python manage.py migrate --noinput && exec gunicorn ...}"

BRANCH="${BRANCH:-main}"
APP_DIR="${APP_DIR:-/app}"
PROJECT_DIR="${PROJECT_DIR:-.}"                # subfolder of the repo that holds manage.py
REQUIREMENTS_FILE="${REQUIREMENTS_FILE:-requirements.txt}"   # relative to PROJECT_DIR
EXTRA_PIP="${EXTRA_PIP:-gunicorn}"             # extra packages the repo doesn't list
PULL_INTERVAL="${PULL_INTERVAL:-60}"           # seconds; 0 = pull once at startup only
HASH_FILE="/opt/venv/.requirements.sha"
# Gitignored API-keys file: mounted from the host, linked into the clone after each pull
API_KEYS_SRC="${API_KEYS_SRC:-/run/secrets/api_keys.txt}"
API_KEYS_DEST="${API_KEYS_DEST:-scripts/api_keys.txt}"   # relative to the repo root

# Private repos: inject token into the clone URL (never echoed to logs)
AUTH_URL="$REPO_URL"
if [ -n "${GITHUB_TOKEN:-}" ]; then
  AUTH_URL="${REPO_URL/https:\/\//https://x-access-token:${GITHUB_TOKEN}@}"
fi

log() { echo "[autopull] $*"; }

# Returns 0 if the checkout changed (or was just cloned), 1 if already current
sync_repo() {
  if [ ! -d "$APP_DIR/.git" ]; then
    log "Cloning $REPO_URL ($BRANCH)..."
    local out
    if ! out="$(git clone --branch "$BRANCH" "$AUTH_URL" "$APP_DIR" 2>&1)"; then
      # Show git's real error, with the token masked
      log "Clone FAILED: ${out//${GITHUB_TOKEN:-@@none@@}/***}"
      return 2
    fi
    return 0
  fi
  git -C "$APP_DIR" remote set-url origin "$AUTH_URL"
  local fetch_out
  if ! fetch_out="$(git -C "$APP_DIR" fetch origin "$BRANCH" 2>&1)"; then
    log "fetch failed, keeping current code: ${fetch_out//${GITHUB_TOKEN:-@@none@@}/***}"
    return 1
  fi
  local local_sha remote_sha
  local_sha="$(git -C "$APP_DIR" rev-parse HEAD)"
  remote_sha="$(git -C "$APP_DIR" rev-parse "origin/$BRANCH")"
  if [ "$local_sha" != "$remote_sha" ]; then
    log "Updating ${local_sha:0:7} -> ${remote_sha:0:7}"
    git -C "$APP_DIR" reset --hard "origin/$BRANCH" >/dev/null
    return 0
  fi
  return 1
}

link_secrets() {
  if [ -f "$API_KEYS_SRC" ]; then
    mkdir -p "$(dirname "$APP_DIR/$API_KEYS_DEST")"
    ln -sf "$API_KEYS_SRC" "$APP_DIR/$API_KEYS_DEST"
  else
    log "WARNING: $API_KEYS_SRC not found, API keys will be missing"
  fi
}

# Only reinstall when the requirements file (or EXTRA_PIP) actually changed
install_deps() {
  local req="$APP_DIR/$PROJECT_DIR/$REQUIREMENTS_FILE"
  if [ ! -f "$req" ]; then
    log "No $PROJECT_DIR/$REQUIREMENTS_FILE found, skipping install"
    return 0
  fi
  local new_hash old_hash=""
  new_hash="$(printf '%s' "$EXTRA_PIP" | cat "$req" - | sha256sum | cut -d' ' -f1)"
  [ -f "$HASH_FILE" ] && old_hash="$(cat "$HASH_FILE")"
  if [ "$new_hash" != "$old_hash" ]; then
    log "Installing Python requirements..."
    # shellcheck disable=SC2086
    pip install --no-cache-dir -r "$req" $EXTRA_PIP
    echo "$new_hash" > "$HASH_FILE"
  else
    log "Requirements unchanged, skipping install"
  fi
}

APP_PID=""
start_app() {
  log "Starting: $START_CMD"
  (cd "$APP_DIR/$PROJECT_DIR" && exec bash -c "$START_CMD") &
  APP_PID=$!
}
stop_app() {
  if [ -n "$APP_PID" ] && kill -0 "$APP_PID" 2>/dev/null; then
    kill "$APP_PID" 2>/dev/null || true
    wait "$APP_PID" 2>/dev/null || true
  fi
}
trap 'stop_app; exit 0' TERM INT

sync_repo || true
if [ ! -d "$APP_DIR/$PROJECT_DIR" ]; then
  log "ERROR: $PROJECT_DIR not found in the cloned repo (or the clone failed). Check REPO_URL, BRANCH, PROJECT_DIR and GITHUB_TOKEN. Retrying in 30s."
  sleep 30
  exit 1
fi
link_secrets
install_deps
start_app

if [ "$PULL_INTERVAL" -le 0 ]; then
  wait "$APP_PID"
  exit $?
fi

while true; do
  sleep "$PULL_INTERVAL" &
  wait $! || true
  # If the app died on its own, exit so Docker's restart policy handles it
  if ! kill -0 "$APP_PID" 2>/dev/null; then
    wait "$APP_PID" 2>/dev/null && code=0 || code=$?
    log "App exited with code $code"
    exit "$code"
  fi
  if sync_repo; then
    link_secrets
    install_deps
    stop_app
    start_app
  fi
done
