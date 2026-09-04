#!/usr/bin/env bash
# Deploy RedditRepostSleuth to a Docker host, over SSH or directly on the host itself.
#
# Usage:
#   ./deploy.sh                     # ship + build + start (first-time on a host)
#   ./deploy.sh --redeploy          # same, but explicit that this updates an existing instance
#   ./deploy.sh --local --redeploy  # run directly on the target (no SSH hop) -- see --local below
#   ./deploy.sh --host mybox.lan    # override any default
#
# Options:
#   --host HOST         SSH target host        (default: prd-docker-01.ho.me)
#   --user USER         SSH user               (default: barry)
#   --dir  DIR          App directory on host  (default: /home/barry/RedditRepostSleuth)
#   --redeploy           No behavioral difference from the default currently -- kept for
#                         parity with the sibling TotalWellness/TrekFauna deploy.sh scripts
#                         and so a future guard (e.g. around .env) has an obvious flag to key off.
#   --no-commit-check    Ship working tree instead of git archive HEAD
#   --local              Run every step directly instead of over SSH -- for when this script
#                         is invoked ON the deploy target itself (the CI runner installed on
#                         prd-docker-01). --host/--user are ignored in this mode.
#
# What this does NOT do:
#   - Deploy docker-compose-public.yml (the public API). That goes to a separate host in
#     the DMZ, not prd-docker-01 -- wiring that up is a separate task. This script only
#     ever touches docker-compose.yml (the worker stack).
#   - Start ingest-svc. It's excluded from `docker compose up -d` via a compose profile
#     (see docker-compose.yml) after a 2026-08-25 incident where restarting it refilled
#     its Redis dataset to 99GB and filled the host disk. Start it manually and watch:
#       docker compose --profile manual up -d ingest
#   - Write or touch sleuth_config.json. It holds real DB/Reddit/Redis/InfluxDB
#     credentials, is gitignored, and must already exist in APP_DIR -- this script
#     only verifies it's there and fails loudly if not.

set -euo pipefail

HOST="prd-docker-01.ho.me"
SSH_USER="barry"
APP_DIR="/home/barry/RedditRepostSleuth"
USE_GIT_ARCHIVE=true
LOCAL=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)            HOST="$2";     shift 2 ;;
    --user)            SSH_USER="$2"; shift 2 ;;
    --dir)             APP_DIR="$2";  shift 2 ;;
    --redeploy)         shift ;;
    --no-commit-check)  USE_GIT_ARCHIVE=false; shift ;;
    --local)            LOCAL=true;   shift   ;;
    *) echo "Unknown flag: $1" >&2; exit 1 ;;
  esac
done

TARGET="${SSH_USER}@${HOST}"

# Executes a command string either over SSH against the deploy target, or directly via a
# fresh local shell when --local is set. Every call site below builds the SAME command
# string either way, so this is the only place that knows which transport is active.
run() {
  if $LOCAL; then
    bash -c "$1"
  else
    ssh "$TARGET" "$1"
  fi
}

# ── Step 0: Prerequisites ────────────────────────────────────────────────────
echo "=== [0/5] Checking prerequisites ==="
run 'docker --version && docker compose version && echo "Groups: $(id)"'
run "test -d ${APP_DIR} && test -w ${APP_DIR} && echo 'App dir WRITABLE' || echo 'App dir missing/not writable -- will attempt mkdir'"

# ── Step 1: Ship source ──────────────────────────────────────────────────────
echo ""
if $LOCAL; then
  echo "=== [1/5] Placing source at ${APP_DIR} (local) ==="
else
  echo "=== [1/5] Shipping source to ${HOST}:${APP_DIR} ==="
fi

if $USE_GIT_ARCHIVE; then
  if ! git diff --quiet HEAD; then
    echo "ERROR: tracked files have uncommitted changes. Commit or pass --no-commit-check." >&2
    git diff --stat HEAD >&2
    exit 1
  fi
  run "mkdir -p ${APP_DIR}"
  # `git archive | tar -x` only ever touches tracked files and is additive -- it
  # never deletes anything already in APP_DIR. That's what makes it safe to run
  # against a directory that also holds gitignored runtime files (sleuth_config.json,
  # .env, logs/, etc.) without wiping them.
  if $LOCAL; then
    git archive HEAD --format=tar | tar -x -C "${APP_DIR}"
  else
    git archive HEAD --format=tar | ssh "$TARGET" "tar -x -C ${APP_DIR}"
  fi
else
  echo "Shipping working tree (bypassing git archive)"
  run "mkdir -p ${APP_DIR}"
  TAR_ARGS=(--exclude-vcs --exclude='logs' --exclude='__pycache__' --exclude='*.pyc')
  if $LOCAL; then
    tar "${TAR_ARGS[@]}" -cf - . | tar -x -C "${APP_DIR}"
  else
    tar "${TAR_ARGS[@]}" -cf - . | ssh "$TARGET" "tar -x -C ${APP_DIR}"
  fi
fi

run "ls ${APP_DIR}" | head -20
echo "Source in place."

# ── Step 2: Required runtime config ──────────────────────────────────────────
echo ""
echo "=== [2/5] Checking runtime config ==="
# sleuth_config.json carries real DB/Reddit/Redis/InfluxDB credentials. It's
# gitignored and this script never writes it -- if it's missing, every service
# would start with empty config and fail (or silently misbehave -- Config falls
# back to None rather than raising). Fail loudly instead.
run "test -f ${APP_DIR}/sleuth_config.json || { echo 'ERROR: ${APP_DIR}/sleuth_config.json is missing. It holds real credentials and is never generated by this script -- place it manually first.' >&2; exit 1; }"
# .env carries no secrets (all real config is in sleuth_config.json) -- docker
# compose just needs the file to exist because docker-compose.yml references it
# via env_file. Safe to create if missing, unlike sleuth_config.json.
run "test -f ${APP_DIR}/.env || { printf 'RUN_ENV=production\nLOG_LEVEL=INFO\n' > ${APP_DIR}/.env; echo 'Wrote minimal .env'; }"
run "echo '.env and sleuth_config.json present'"

# ── Step 3: Build and start ──────────────────────────────────────────────────
echo ""
echo "=== [3/4] Building and starting worker stack ==="
run "cd ${APP_DIR} && docker compose build 2>&1 | tail -30"
run "cd ${APP_DIR} && docker compose up -d"

# ── Step 4: Verify ───────────────────────────────────────────────────────────
echo ""
echo "=== [4/4] Verifying ==="
run "cd ${APP_DIR} && docker compose ps --format 'table {{.Name}}\t{{.Status}}'"

echo ""
echo "--- Container health check ---"
# Plain-text grep on the Status column rather than parsing `docker compose ps --format
# json` -- its shape (single array vs newline-delimited objects) has changed across
# compose versions, and grepping for the literal "(unhealthy)"/"Restarting" text compose
# prints is stable regardless.
run "cd ${APP_DIR} && docker compose ps --format 'table {{.Name}}\t{{.Status}}' > /tmp/repostsleuth-deploy-status.txt; cat /tmp/repostsleuth-deploy-status.txt; if grep -qiE 'unhealthy|restarting' /tmp/repostsleuth-deploy-status.txt; then echo 'ERROR: one or more containers are unhealthy/restarting' >&2; exit 1; else echo 'All services healthy'; fi"

echo ""
echo "=== Deploy complete ==="
echo "NOTE: ingest-svc was NOT started (excluded via compose profile -- see top of this file)."
echo "Start it manually once you're ready to watch it: docker compose --profile manual up -d ingest"
