#!/bin/bash
# Decay And Conquer — GCE VM startup script
# Runs once on first boot. Installs everything, configures services.
set -euo pipefail
exec > /var/log/startup-script.log 2>&1
echo "=== Startup script started at $(date) ==="

APP_USER="${ssh_user}"
APP_DIR="/opt/decay_core"
DATA_DIR="/data/decay"
DEVICE="/dev/disk/by-id/google-decay-data"

# ---------------------------------------------------------------
# 1. System packages
# ---------------------------------------------------------------
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-dev \
  nginx certbot python3-certbot-nginx \
  git jq flock logrotate

# Node.js 20 via NodeSource
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y -qq nodejs

# ---------------------------------------------------------------
# 2. Create app user
# ---------------------------------------------------------------
id "$APP_USER" &>/dev/null || useradd -m -s /bin/bash "$APP_USER"
mkdir -p /var/log/decay
chown "$APP_USER:$APP_USER" /var/log/decay

# ---------------------------------------------------------------
# 3. Format and mount data disk (idempotent)
# ---------------------------------------------------------------
mkdir -p "$DATA_DIR"
if ! blkid "$DEVICE" | grep -q ext4; then
  echo "Formatting data disk..."
  mkfs.ext4 -F -m 0 -E lazy_itable_init=0,lazy_journal_init=0 "$DEVICE"
fi
if ! mountpoint -q "$DATA_DIR"; then
  mount "$DEVICE" "$DATA_DIR"
fi
grep -q "$DEVICE" /etc/fstab || echo "$DEVICE $DATA_DIR ext4 defaults,nofail 0 2" >> /etc/fstab
mkdir -p "$DATA_DIR"/{db,flat_files}
chown -R "$APP_USER:$APP_USER" "$DATA_DIR"

# ---------------------------------------------------------------
# 4. Clone app
# ---------------------------------------------------------------
if [ ! -d "$APP_DIR/.git" ]; then
  git clone "${app_repo_url}" "$APP_DIR"
else
  cd "$APP_DIR" && git pull --ff-only || true
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# ---------------------------------------------------------------
# 5. Fetch secrets and write .env
# ---------------------------------------------------------------
MASSIVE_KEY=$(gcloud secrets versions access latest --secret=massive-api-key 2>/dev/null || echo "")
ANTHROPIC_KEY=$(gcloud secrets versions access latest --secret=anthropic-api-key 2>/dev/null || echo "")
GOOGLE_KEY=$(gcloud secrets versions access latest --secret=google-api-key 2>/dev/null || echo "")

cat > "$APP_DIR/.env" <<EOF
MASSIVE_API_KEY=$MASSIVE_KEY
ANTHROPIC_API_KEY=$ANTHROPIC_KEY
GOOGLE_API_KEY=$GOOGLE_KEY
EOF
chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"

# ---------------------------------------------------------------
# 6. Python venv + dependencies
# ---------------------------------------------------------------
cd "$APP_DIR/backend"
sudo -u "$APP_USER" python3 -m venv .venv
sudo -u "$APP_USER" .venv/bin/pip install --upgrade pip -q
sudo -u "$APP_USER" .venv/bin/pip install -r requirements.txt -q

# ---------------------------------------------------------------
# 7. Symlink DuckDB + flat_files to data disk
# ---------------------------------------------------------------
ln -sf "$DATA_DIR/db/options.duckdb" "$APP_DIR/backend/app/data/options.duckdb"
ln -sf "$DATA_DIR/flat_files" "$APP_DIR/backend/app/data/flat_files"

# ---------------------------------------------------------------
# 8. Build frontend
# ---------------------------------------------------------------
cd "$APP_DIR/frontend"
sudo -u "$APP_USER" npm ci --silent
sudo -u "$APP_USER" env VITE_API_BASE="" npm run build

# ---------------------------------------------------------------
# 9. Systemd service for uvicorn
# ---------------------------------------------------------------
cat > /etc/systemd/system/decay-api.service <<SVCEOF
[Unit]
Description=Decay And Conquer API
After=network.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR/backend
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 6173 --workers 2
Restart=always
RestartSec=5
StandardOutput=append:/var/log/decay/api.log
StandardError=append:/var/log/decay/api.log

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable decay-api
systemctl start decay-api

# ---------------------------------------------------------------
# 10. Nginx configuration
# ---------------------------------------------------------------
cat > /etc/nginx/sites-available/decay <<'NGINXEOF'
server {
    listen 80 default_server;
    server_name _;

    root /opt/decay_core/frontend/dist;
    index index.html;

    # API proxy (matches all backend routes)
    location ~ ^/(chat|predict|predict-stream|market-context|theta-plays|theta-expiries|heatmap-stream|theta-plays-stream|ping) {
        proxy_pass http://127.0.0.1:6173;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection '';

        # SSE support — do not buffer streamed responses
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }

    # SPA fallback — all other routes serve index.html
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache static assets
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff2?)$ {
        expires 7d;
        add_header Cache-Control "public, immutable";
    }
}
NGINXEOF

rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/decay /etc/nginx/sites-enabled/
nginx -t && systemctl restart nginx

# ---------------------------------------------------------------
# 11. Certbot (if domain is set)
# ---------------------------------------------------------------
DOMAIN="${domain_name}"
if [ -n "$DOMAIN" ]; then
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email "admin@$DOMAIN" || echo "Certbot failed — DNS may not be configured yet"
fi

# ---------------------------------------------------------------
# 12. Sudoers for cron jobs (stop/start API without password)
# ---------------------------------------------------------------
cat > /etc/sudoers.d/decay-api <<SUDOEOF
$APP_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop decay-api
$APP_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl start decay-api
$APP_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart decay-api
SUDOEOF
chmod 440 /etc/sudoers.d/decay-api

# ---------------------------------------------------------------
# 13. Install daily cron job
# ---------------------------------------------------------------
cp "$APP_DIR/terraform/scripts/run-daily-jobs.sh" /opt/decay_core/scripts/run-daily-jobs.sh
chmod +x /opt/decay_core/scripts/run-daily-jobs.sh
chown "$APP_USER:$APP_USER" /opt/decay_core/scripts/run-daily-jobs.sh

# Run at 9:30 UTC (5:30 AM ET during EDT) weekdays
cat > /etc/cron.d/decay-daily <<CRONEOF
SHELL=/bin/bash
30 9 * * 1-5 $APP_USER /opt/decay_core/scripts/run-daily-jobs.sh >> /var/log/decay/cron.log 2>&1
CRONEOF

# ---------------------------------------------------------------
# 14. Log rotation
# ---------------------------------------------------------------
cat > /etc/logrotate.d/decay <<LOGEOF
/var/log/decay/*.log {
    weekly
    rotate 4
    compress
    missingok
    notifempty
    copytruncate
}
LOGEOF

echo "=== Startup script completed at $(date) ==="
