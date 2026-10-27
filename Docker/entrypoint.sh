#!/usr/bin/env bash
# Clones a GitHub repo, installs requirements, runs the app, and
# periodically pulls updates (reinstalling deps and restarting on change).
set -euo pipefail

: "${REPO_URL:?Set REPO_URL, e.g. https://github.com/you/yourrepo.git}"
: "${START_CMD:?Set START_CMD, e.g. python main.py}"

BRANCH="${BRANCH:-main}"
APP_DIR="${APP_DIR:-/app}"
PULL_INTERVAL="${PULL_INTERVAL:-60}"   # seconds; 0 = pull once at startup only
HASH_FILE="/opt/venv/.requirements.sha"

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
    git clone --branch "$BRANCH" "$AUTH_URL" "$APP_DIR" >/dev/null 2>&1
    return 0
  fi
  git -C "$APP_DIR" remote set-url origin "$AUTH_URL"
  git -C "$APP_DIR" fetch origin "$BRANCH" >/dev/null 2>&1 || { log "fetch failed, keeping current code"; return 1; }
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

# Only reinstall when requirements.txt actually changed
install_deps() {
  if [ -f "$APP_DIR/requirements.txt" ]; then
    local new_hash old_hash=""
    new_hash="$(sha256sum "$APP_DIR/requirements.txt" | cut -d' ' -f1)"
    [ -f "$HASH_FILE" ] && old_hash="$(cat "$HASH_FILE")"
    if [ "$new_hash" != "$old_hash" ]; then
      log "Installing Python requirements..."
      pip install --no-cache-dir -r "$APP_DIR/requirements.txt"
      echo "$new_hash" > "$HASH_FILE"
    else
      log "requirements.txt unchanged, skipping install"
    fi
  else
    log "No requirements.txt found, skipping install"
  fi
}

APP_PID=""
start_app() {
  log "Starting: $START_CMD"
  (cd "$APP_DIR" && exec bash -c "$START_CMD") &
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
    install_deps
    stop_app
    start_app
  fi
done
