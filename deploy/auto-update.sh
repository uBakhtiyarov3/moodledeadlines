#!/bin/sh
# Pull new commits of the deployed branch and rebuild the bot when there are any.
# Runs from cron every 5 minutes (see enable-auto-update.sh); safe to run by hand too.
# If the build fails, the running container is left untouched.
set -eu
cd "$(dirname "$0")/.."

exec 9>/tmp/uwed-update.lock
flock -n 9 || exit 0  # a previous update is still building

git fetch -q origin
old=$(git rev-parse HEAD)
new=$(git rev-parse '@{u}')
[ "$old" = "$new" ] && [ "${1:-}" != "--force" ] && exit 0

git merge -q --ff-only '@{u}'
sudo docker compose up -d --build
sudo docker image prune -f >/dev/null  # the VM disk is small; drop old builds
echo "$(date '+%F %T') updated $(git rev-parse --short "$old") -> $(git rev-parse --short "$new")"
