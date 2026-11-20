#!/usr/bin/env bash
# One-shot, idempotent setup of the JD Quant Streamlit dashboard on the DO droplet.
# Run as root on the droplet:  bash setup_droplet.sh
#
# - Clones the public repo to /opt/jdquant (or updates it)
# - Creates a venv with dashboard deps
# - Runs Streamlit as systemd service `jdquant-dashboard` on 127.0.0.1:8501
# - Puts HTTPS in front: reuses nginx (+certbot) if nginx is already running
#   on this box (e.g. klassi.in), otherwise installs Caddy (auto-HTTPS)
# - Installs a 5-minute timer that git-pulls and restarts on new commits
#   (replaces Render's auto-deploy; GH Actions data commits show up within 5 min)
set -euo pipefail

REPO_URL="https://github.com/zeevandeep/trading-dashboard.git"
APP_DIR="/opt/jdquant"
DOMAINS=("jdquant.in" "www.jdquant.in")
CERT_EMAIL="${CERT_EMAIL:-}"   # optional, for Let's Encrypt expiry notices

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git python3 python3-venv python3-pip curl >/dev/null

# Small droplets: add 1 GB swap so pip/streamlit don't get OOM-killed
if ! swapon --show | grep -q . ; then
  fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# ── Code ──────────────────────────────────────────────────────────────────────
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch -q origin main && git -C "$APP_DIR" reset -q --hard origin/main
else
  git clone -q --depth 50 "$REPO_URL" "$APP_DIR"
fi

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements-dashboard.txt"

# ── Streamlit service ────────────────────────────────────────────────────────
cp "$APP_DIR/deploy/jdquant-dashboard.service" /etc/systemd/system/
cp "$APP_DIR/deploy/jdquant-update.service"    /etc/systemd/system/
cp "$APP_DIR/deploy/jdquant-update.timer"      /etc/systemd/system/
install -m 755 "$APP_DIR/deploy/update.sh" /usr/local/bin/jdquant-update
systemctl daemon-reload
systemctl enable --now jdquant-dashboard.service
systemctl enable --now jdquant-update.timer

# ── HTTPS reverse proxy ──────────────────────────────────────────────────────
if systemctl is-active --quiet nginx; then
  echo ">> nginx already running — adding a server block + certbot"
  cp "$APP_DIR/deploy/nginx-jdquant.conf" /etc/nginx/sites-available/jdquant
  ln -sf /etc/nginx/sites-available/jdquant /etc/nginx/sites-enabled/jdquant
  nginx -t && systemctl reload nginx
  # Use snap certbot: apt's certbot crashes on this box because pip-installed
  # cryptography/pyOpenSSL in /usr/local/lib/python3.12 shadow the apt versions.
  if [ "$(readlink -f "$(command -v certbot 2>/dev/null)")" != "/snap/bin/certbot" ]; then
    apt-get remove -y -qq certbot python3-certbot-nginx >/dev/null 2>&1 || true
    snap install --classic certbot
    ln -sf /snap/bin/certbot /usr/bin/certbot
  fi
  certbot renew --quiet || true   # also renews other sites on this box (klassi.in)
  EMAIL_ARGS=(--register-unsafely-without-email); [ -n "$CERT_EMAIL" ] && EMAIL_ARGS=(-m "$CERT_EMAIL")
  # Only succeeds once DNS points here; safe to re-run later
  certbot --nginx --non-interactive --agree-tos "${EMAIL_ARGS[@]}" --redirect \
    $(printf -- '-d %s ' "${DOMAINS[@]}") || echo "!! certbot failed — point DNS at this droplet, then re-run this script"
else
  echo ">> installing Caddy (automatic HTTPS)"
  if ! command -v caddy >/dev/null; then
    apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https gnupg >/dev/null
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -qq && apt-get install -y -qq caddy >/dev/null
  fi
  cp "$APP_DIR/deploy/Caddyfile" /etc/caddy/Caddyfile
  systemctl enable caddy && systemctl reload-or-restart caddy
fi

# Open web ports if ufw is on (port 8001 rules for the order proxy are untouched)
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null
fi

sleep 5
curl -fsS http://127.0.0.1:8501/_stcore/health && echo "  <- streamlit healthy"
echo "Done. Point jdquant.in + www A records at $(curl -fsS https://api.ipify.org 2>/dev/null || echo this droplet)."
