#!/bin/sh
# Bring the bot up to date: pull the deployed branch and rebuild whenever the running build is not
# the checked-out commit (also after a manual `git pull`). Runs from cron every 5 minutes (see
# enable-auto-update.sh); safe to run by hand. A failed build leaves the running container untouched.
set -eu
cd "$(dirname "$0")/.."

exec 9>"$HOME/.uwed-update.lock"
if ! flock -n 9; then
  echo "$(date '+%F %T') another update is still running"
  exit 0
fi

git fetch -q origin
git merge -q --ff-only '@{u}'
head=$(git rev-parse HEAD)
built=$(cat .deployed 2>/dev/null || true)
if [ "$head" = "$built" ] && [ "${1:-}" != "--force" ]; then
  exit 0  # the running bot is already this commit
fi

echo "$(date '+%F %T') building $(git rev-parse --short HEAD)…"
sudo docker compose up -d --build
echo "$head" > .deployed
sudo docker image prune -f >/dev/null  # the VM disk is small; drop old builds
echo "$(date '+%F %T') running $(git log -1 --format='%h %s')"
