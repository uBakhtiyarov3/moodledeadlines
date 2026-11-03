#!/bin/sh
# One-time: update the bot automatically every 5 minutes from GitHub, then update right now.
set -eu
cd "$(dirname "$0")/.."
dir=$(pwd)
command -v crontab >/dev/null || sudo apt-get install -y -qq cron
line="*/5 * * * * sh $dir/deploy/auto-update.sh >> $HOME/uwed-update.log 2>&1"

(crontab -l 2>/dev/null | grep -v 'deploy/auto-update.sh' || true; echo "$line") | crontab -
echo "==> Auto-update on: every 5 minutes. Log: ~/uwed-update.log"
sh deploy/auto-update.sh --force
echo "==> Done. The bot now updates itself; no more SSH needed for updates."
