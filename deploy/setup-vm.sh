#!/usr/bin/env bash
# One-shot server setup for Debian/Ubuntu (GCP e2-micro, Oracle Always Free, any VPS).
# Usage on the VM:
#   curl -fsSL https://raw.githubusercontent.com/uBakhtiyarov3/moodledeadlines/main/deploy/setup-vm.sh | bash
set -euo pipefail

REPO="${REPO:-https://github.com/uBakhtiyarov3/moodledeadlines.git}"
BRANCH="${BRANCH:-main}"
DIR="${DIR:-$HOME/uwed-bot}"

echo "==> Swap (e2-micro has only 1 GB RAM)"
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "==> Docker"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
fi

echo "==> Code"
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" pull --ff-only
else
  sudo apt-get update -qq && sudo apt-get install -y -qq git >/dev/null
  git clone --branch "$BRANCH" "$REPO" "$DIR"
fi
cd "$DIR"

if [ ! -f .env ]; then
  cp .env.example .env
  IP=$(curl -fsS https://api.ipify.org)
  DOMAIN="${IP//./-}.sslip.io"
  SECRET=$(python3 -c "import secrets;print(secrets.token_urlsafe(48))")
  sed -i "s|^PUBLIC_URL=.*|PUBLIC_URL=https://$DOMAIN|; s|^DOMAIN=.*|DOMAIN=$DOMAIN|; s|^SECRET_KEY=.*|SECRET_KEY=$SECRET|" .env
  echo
  echo "!! .env created with PUBLIC_URL=https://$DOMAIN"
  echo "!! Fill in BOT_TOKEN, ADMIN_IDS and GEMINI_API_KEY:"
  echo "     nano $DIR/.env"
  echo "!! then run:  cd $DIR && sudo docker compose up -d --build"
  exit 0
fi

mkdir -p data
sudo docker compose up -d --build
sudo docker compose ps
echo "==> Done. Logs: cd $DIR && sudo docker compose logs -f bot"
