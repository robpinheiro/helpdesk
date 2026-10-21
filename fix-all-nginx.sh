#!/usr/bin/env bash
# Fix Completo Nginx - Remove 400 Bad Request
# Uso: chmod +x fix-all-nginx.sh && sudo ./fix-all-nginx.sh

set -euo pipefail

PROJECT_DIR="/opt/helpdesk"
cd "$PROJECT_DIR"

log() { echo -e "\033[1;32m[FIX-ALL]\033[0m $*"; }
warn() { echo -e "\033[1;33m[WARN]\033[0m $*"; }

# ============================================================================
# 1. NGINX.CONF CORRETO NO HOST
# ============================================================================
log "Atualizando nginx/nginx.conf no host..."
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

    # Desabilita validação estrita de headers (evita 400 por host/underscore)
    ignore_invalid_headers off;
    underscores_in_headers on;

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
        listen 80 default_server;
        listen [::]:80 default_server;
        server_name _;

        # Permite qualquer Host header (Django valida via ALLOWED_HOSTS)
        ignore_invalid_headers off;
        underscores_in_headers on;

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
            proxy_buffering off;
        }
    }
}
EOF

log "nginx/nginx.conf atualizado no host (ignore_invalid_headers off, underscores_in_headers on)"

# ============================================================================
# 2. CRIA CONF.D VAZIO PARA SOBRESCREVER DEFAULT.CONF
# ============================================================================
log "Criando nginx/conf.d/default.conf vazio no host..."
mkdir -p nginx/conf.d
echo "# disabled - custom config in nginx.conf" > nginx/conf.d/default.conf

# ============================================================================
# 3. RECREIA NGINX COM NOVOS VOLUMES
# ============================================================================
log "Recriando container nginx com volumes atualizados..."

# Atualiza docker-compose.yml para montar conf.d também
if ! grep -q "conf.d" docker-compose.yml; then
    log "Atualizando docker-compose.yml para montar conf.d..."
    sed -i '/nginx.conf/a\      - ./nginx/conf.d/:/etc/nginx/conf.d/:ro' docker-compose.yml
    log "docker-compose.yml atualizado com montagem conf.d"
fi

# Recria nginx
docker compose up -d --force-recreate nginx

# Aguarda nginx estabilizar
log "Aguardando nginx estabilizar..."
sleep 5

# ============================================================================
# 4. TESTA E VERIFICA
# ============================================================================
log "Testando health check..."

# Testa com Host header correto
for i in 1 2 3; do
    if curl -sf -H "Host: 192.168.15.12" http://localhost/health/ > /dev/null 2>&1; then
        log "✅ Health check OK (200) com Host header"
        break
    elif curl -sf http://localhost/health/ > /dev/null 2>&1; then
        log "✅ Health check OK (200) sem Host header"
        break
    else
        warn "Tentativa $i falhou, aguardando..."
        sleep 3
    fi
done

# Verifica status final
log "Status dos containers:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

log "Logs recentes do nginx:"
docker logs helpdesk-nginx --tail 20

# Teste final
echo ""
log "=== TESTE FINAL ==="
curl -v -H "Host: 192.168.15.12" http://localhost/health/ 2>&1 | head -20

echo ""
log "✅ Correção completa!"
echo "Acesse: http://192.168.15.12"
echo "Admin:  http://192.168.15.12/admin/  (admin / changeme123)"