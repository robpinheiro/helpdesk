#!/usr/bin/env bash
# Fix Nginx - Recria container com config corrigida
# Uso: chmod +x fix-nginx.sh && sudo ./fix-nginx.sh

set -euo pipefail

PROJECT_DIR="/opt/helpdesk"
cd "$PROJECT_DIR"

log() { echo -e "\033[1;32m[FIX-NGINX]\033[0m $*"; }

# 1. Garante nginx.conf correto no host
log "Atualizando nginx/nginx.conf..."
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

log "nginx.conf atualizado (sem proxy_params, http2 moderno)"

# 2. Recria APENAS o nginx (pega config novo via volume)
log "Recriando container nginx com config nova..."
docker compose up -d --force-recreate nginx

# 3. Aguarda e verifica
log "Aguardando nginx subir..."
sleep 5

log "Logs do nginx:"
docker logs helpdesk-nginx --tail 20

# 4. Testa
log "Testando health check..."
if curl -sf http://localhost/health/ > /dev/null; then
    log "✅ Health check OK (200)"
else
    log "❌ Health check falhou - mostrando logs:"
    docker logs helpdesk-nginx --tail 30
    exit 1
fi

log "Testando com Host header:"
curl -sf -H "Host: 192.168.15.12" http://localhost/health/ && log "✅ Host header OK"

echo ""
log "✅ Nginx corrigido e funcionando!"
echo "Acesse: http://192.168.15.12"
echo "Admin:  http://192.168.15.12/admin/  (admin / changeme123)"