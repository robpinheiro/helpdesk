#!/usr/bin/env bash
# Fix Celery + Nginx para Helpdesk
# Uso: chmod +x fix-celery-nginx.sh && sudo ./fix-celery-nginx.sh

set -euo pipefail

PROJECT_DIR="/opt/helpdesk"
cd "$PROJECT_DIR"

log() { echo -e "\033[1;32m[FIX]\033[0m $*"; }

# 1. Cria config/celery.py
log "Criando config/celery.py..."
cat > config/celery.py << 'EOF'
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

app = Celery('helpdesk')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
EOF

# 2. Corrige nginx.conf
log "Corrigindo nginx.conf..."
cat > nginx/nginx.conf << 'EOF'
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';
    access_log /var/log/nginx/access.log main;

    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/xml+rss application/json;

    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;

    upstream web {
        server web:8000;
    }

    server {
        listen 80;
        listen [::]:80;
        server_name _;

        client_max_body_size 20M;

        location /static/ {
            alias /var/www/static/;
            expires 30d;
            add_header Cache-Control "public";
        }

        location /media/ {
            alias /var/www/media/;
            expires 7d;
            add_header Cache-Control "public";
        }

        location /health/ {
            proxy_pass http://web/health/;
            access_log off;
        }

        location / {
            proxy_pass http://web;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 120s;
            proxy_send_timeout 120s;
        }
    }
}
EOF

# 3. Rebuild e reinicia
log "Rebuild e restart dos containers..."
docker compose build
docker compose up -d

# 4. Verifica
log "Aguardando containers subirem..."
sleep 8

log "Status dos containers:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

log "Testando health check..."
curl -sf http://192.168.15.12/health/ && echo " - OK" || echo " - FALHOU"

log "Concluído!"
echo ""
echo "Acesse: http://192.168.15.12"
echo "Admin:  http://192.168.15.12/admin/  (admin / changeme123)"