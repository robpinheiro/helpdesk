#!/usr/bin/env bash
# ============================================================================
# Helpdesk - Setup Direto (Sem Nginx, Porta 8000)
# ============================================================================
# Uso: chmod +x setup-direct.sh && sudo ./setup-direct.sh
# Faz TUDO do zero: limpa, cria user, clona, configura, sobe direto na 8000
# ============================================================================

set -euo pipefail

REPO_URL="https://github.com/robpinheiro/helpdesk.git"
PROJECT_DIR="/opt/helpdesk"
APP_USER="helpdesk"
DB_NAME="helpdesk"
DB_USER="helpdesk"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()   { echo -e "${BLUE}[SETUP]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

[[ $EUID -eq 0 ]] || { error "Execute como root: sudo ./setup-direct.sh"; exit 1; }

# ============================================================================
# COLETA DE CONFIGURAÇÕES
# ============================================================================
echo
log "=== Helpdesk - Setup Direto (Porta 8000, Sem Nginx) ==="
echo

ask() {
    local prompt="$1" var="$2" default="${3:-}" val=""
    [[ -n "$default" ]] && read -rp "$prompt [$default]: " val || read -rp "$prompt: " val
    val="${val:-$default}"
    [[ -z "$val" && -z "$default" ]] && { warn "Obrigatório!"; ask "$1" "$2" "$3"; return; }
    printf -v "$var" '%s' "$val"
}

ask_secret() {
    local prompt="$1" var="$2" val=""
    read -rsp "$prompt: " val; echo
    [[ -z "$val" ]] && { warn "Obrigatório!"; ask_secret "$1" "$2"; return; }
    printf -v "$var" '%s' "$val"
}

DETECTED_IP=$(ip route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}' || hostname -I | awk '{print $1}')

log "=== Configuração Inicial ==="
ask "IP do servidor para acesso" SERVER_IP "$DETECTED_IP"
ask "Timezone" TIMEZONE "America/Sao_Paulo"
ask "Swap size" SWAP_SIZE "2G"

log "=== Banco de Dados ==="
ask "Usuário PostgreSQL" DB_USER "$DB_USER"
ask_secret "Senha PostgreSQL" DB_PASSWORD
ask "Nome do banco" DB_NAME "$DB_NAME"

log "=== Django ==="
ask_secret "SECRET_KEY (python -c \"import secrets; print(secrets.token_urlsafe(50))\")" SECRET_KEY
ALLOWED_HOSTS="$SERVER_IP,localhost,127.0.0.1,0.0.0.0"
CSRF_TRUSTED_ORIGINS="http://$SERVER_IP,http://$SERVER_IP:8000"
log "ALLOWED_HOSTS: $ALLOWED_HOSTS"
log "CSRF_TRUSTED_ORIGINS: $CSRF_TRUSTED_ORIGINS"

log "=== LDAP (opcional - configure depois no Admin) ==="
ask "LDAP URI" LDAP_URI "ldap://samba4.interno:389"
ask "LDAP Bind DN" LDAP_BIND_DN "cn=helpdesk,ou=services,dc=empresa,dc=local"
ask_secret "LDAP Bind Password" LDAP_BIND_PASSWORD

log "=== Email/SMTP (opcional) ==="
ask "SMTP Host" SMTP_HOST "smtp.empresa.local"
ask "SMTP Port" SMTP_PORT "587"
ask "SMTP User" SMTP_USER "helpdesk@empresa.local"
ask_secret "SMTP Password" SMTP_PASSWORD
ask "SMTP From" SMTP_FROM "Helpdesk <helpdesk@empresa.local>"

log "=== Backup ==="
ask "Diretório de backup" BACKUP_DIR "/mnt/backups/helpdesk"
ask "Retenção (dias)" BACKUP_RETENTION "30"

# ============================================================================
# 1. LIMPEZA TOTAL
# ============================================================================
log "=== [1/9] Limpando ambiente anterior ==="
cd /opt 2>/dev/null || true
docker compose -f "$PROJECT_DIR/docker-compose.yml" down -v --remove-orphans 2>/dev/null || true
docker system prune -af --volumes 2>/dev/null || true
rm -rf "$PROJECT_DIR"
ok "Limpeza completa"

# ============================================================================
# 2. SISTEMA BASE
# ============================================================================
log "=== [2/9] Sistema base ==="
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq
timedatectl set-timezone "$TIMEZONE"
locale-gen pt_BR.UTF-8
update-locale LANG=pt_BR.UTF-8

# Swap
if ! swapon --show | grep -q '/swapfile'; then
    fallocate -l "$SWAP_SIZE" /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    ok "Swap $SWAP_SIZE criado"
fi

# Dependências
apt-get install -y -qq \
    curl wget gnupg2 software-properties-common \
    apt-transport-https ca-certificates lsb-release \
    git vim htop net-tools ufw fail2ban \
    python3 python3-venv python3-pip \
    postgresql-client redis-tools
ok "Dependências base instaladas"

# Docker
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    ok "Docker instalado"
else
    warn "Docker já presente"
fi
docker compose version &>/dev/null || { apt-get install -y -qq docker-compose-plugin; ok "Docker Compose plugin"; }

# ============================================================================
# 3. USUÁRIO E PERMISSÕES
# ============================================================================
log "=== [3/9] Usuário helpdesk e permissões ==="
if id "$APP_USER" &>/dev/null; then
    usermod -aG docker "$APP_USER"
else
    useradd -m -s /bin/bash -G docker "$APP_USER"
    ok "Usuário $APP_USER criado"
fi

# Diretório do projeto com dono correto
mkdir -p "$PROJECT_DIR"
chown "$APP_USER:$APP_USER" "$PROJECT_DIR"
chmod 755 "$PROJECT_DIR"
ok "Diretório $PROJECT_DIR criado com owner $APP_USER"

# ============================================================================
# 4. CLONE DO REPOSITÓRIO
# ============================================================================
log "=== [4/9] Clonando repositório ==="
sudo -u "$APP_USER" git clone "$REPO_URL" "$PROJECT_DIR"
cd "$PROJECT_DIR"
ok "Repositório clonado em $PROJECT_DIR"

# ============================================================================
# 5. CORREÇÕES NO CÓDIGO (SEM NGINX, DIRETO NA 8000)
# ============================================================================
log "=== [5/9] Aplicando correções (sem nginx, direto 8000) ==="

# 5.1 config/celery.py
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

# 5.2 requirements/base.txt - adiciona ldap3
grep -q "^ldap3" requirements/base.txt || echo "ldap3>=2.9" >> requirements/base.txt

# 5.3 docker-compose.yml - SEM NGINX, COM PORTA 8000 NO WEB
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    container_name: helpdesk-postgres
    environment:
      POSTGRES_DB: helpdesk
      POSTGRES_USER: ${DB_USER:-helpdesk}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER:-helpdesk}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - internal
    deploy:
      resources:
        limits:
          memory: 512M
        reservations:
          memory: 256M

  redis:
    image: redis:7-alpine
    container_name: helpdesk-redis
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    networks:
      - internal
    deploy:
      resources:
        limits:
          memory: 256M
        reservations:
          memory: 128M

  web:
    image: ${REGISTRY:-local}/helpdesk-web:${TAG:-latest}
    container_name: helpdesk-web
    build:
      context: .
      dockerfile: Dockerfile
    command: gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers ${WEB_WORKERS:-3} --timeout 60 --access-logfile -
    environment:
      - DEBUG=${DEBUG:-0}
      - DJANGO_SETTINGS_MODULE=config.settings.production
      - DB_HOST=postgres
      - DB_NAME=helpdesk
      - DB_USER=${DB_USER:-helpdesk}
      - DB_PASSWORD=${DB_PASSWORD}
      - REDIS_URL=redis://redis:6379/0
      - LDAP_URI=${LDAP_URI}
      - LDAP_BIND_DN=${LDAP_BIND_DN}
      - LDAP_BIND_PASSWORD=${LDAP_BIND_PASSWORD}
      - SECRET_KEY=${SECRET_KEY}
      - ALLOWED_HOSTS=${ALLOWED_HOSTS:-*}
      - CSRF_TRUSTED_ORIGINS=${CSRF_TRUSTED_ORIGINS}
      - SMTP_HOST=${SMTP_HOST}
      - SMTP_PORT=${SMTP_PORT:-587}
      - SMTP_USER=${SMTP_USER}
      - SMTP_PASSWORD=${SMTP_PASSWORD}
      - SMTP_FROM=${SMTP_FROM}
      - SMTP_USE_TLS=${SMTP_USE_TLS:-True}
      - SMTP_USE_SSL=${SMTP_USE_SSL:-False}
    ports:
      - "8000:8000"
    volumes:
      - media_files:/app/media
      - static_files:/app/static
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - internal
    deploy:
      resources:
        limits:
          memory: 1G
        reservations:
          memory: 512M
    restart: unless-stopped

  celery:
    image: ${REGISTRY:-local}/helpdesk-web:${TAG:-latest}
    container_name: helpdesk-celery
    command: celery -A config worker -l INFO -Q default,emails,reports,backups --concurrency=4
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.production
      - DB_HOST=postgres
      - DB_NAME=helpdesk
      - DB_USER=${DB_USER:-helpdesk}
      - DB_PASSWORD=${DB_PASSWORD}
      - REDIS_URL=redis://redis:6379/0
      - LDAP_URI=${LDAP_URI}
      - LDAP_BIND_DN=${LDAP_BIND_DN}
      - LDAP_BIND_PASSWORD=${LDAP_BIND_PASSWORD}
      - SECRET_KEY=${SECRET_KEY}
    volumes:
      - media_files:/app/media
    depends_on:
      - postgres
      - redis
    networks:
      - internal
    deploy:
      resources:
        limits:
          memory: 512M
        reservations:
          memory: 256M
    restart: unless-stopped

  celery-beat:
    image: ${REGISTRY:-local}/helpdesk-web:${TAG:-latest}
    container_name: helpdesk-celery-beat
    command: celery -A config beat -l INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.production
      - DB_HOST=postgres
      - DB_NAME=helpdesk
      - DB_USER=${DB_USER:-helpdesk}
      - DB_PASSWORD=${DB_PASSWORD}
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=${SECRET_KEY}
    depends_on:
      - postgres
      - redis
    networks:
      - internal
    deploy:
      resources:
        limits:
          memory: 256M
        reservations:
          memory: 128M
    restart: unless-stopped

networks:
  internal:
    driver: bridge
    internal: true

volumes:
  postgres_data:
    name: helpdesk_postgres_data
  redis_data:
    name: helpdesk_redis_data
  media_files:
    name: helpdesk_media_files
  static_files:
    name: helpdesk_static_files
EOF

# 5.4 Dockerfile - base bookworm para libldap-2.5-0 (só corrige se não tiver bookworm)
sed -i 's/FROM python:3.12-slim$/FROM python:3.12-slim-bookworm/' Dockerfile

# 5.5 apps/accounts/admin.py - remove is_tecnico do list_filter
sed -i "s/'is_tecnico', //g" apps/accounts/admin.py
sed -i "s/, 'is_tecnico'//g" apps/accounts/admin.py
sed -i "s/'is_tecnico'//g" apps/accounts/admin.py

# 5.6 apps/tickets/models.py - remove change_reason_field depreciado
sed -i '/change_reason_field=models.TextField/d' apps/tickets/models.py
sed -i '/change_reason_field=/,/)/d' apps/tickets/models.py
# Fix mais robusto:
sed -i 's/change_reason_field=models.TextField(_("Motivo da Alteração"), blank=True)//g' apps/tickets/models.py

# Ajusta permissões
chown -R "$APP_USER:$APP_USER" "$PROJECT_DIR"
ok "Correções aplicadas (celery, compose sem nginx, dockerfile, admin, models)"

# ============================================================================
# 6. ARQUIVO .ENV
# ============================================================================
log "=== [6/9] Gerando .env ==="
cat > .env << EOF
REGISTRY=
TAG=latest
DEBUG=0
SECRET_KEY=$SECRET_KEY
ALLOWED_HOSTS=$ALLOWED_HOSTS
CSRF_TRUSTED_ORIGINS=$CSRF_TRUSTED_ORIGINS
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
DB_NAME=$DB_NAME
LDAP_URI=$LDAP_URI
LDAP_BIND_DN=$LDAP_BIND_DN
LDAP_BIND_PASSWORD=$LDAP_BIND_PASSWORD
SMTP_HOST=$SMTP_HOST
SMTP_PORT=$SMTP_PORT
SMTP_USER=$SMTP_USER
SMTP_PASSWORD=$SMTP_PASSWORD
SMTP_FROM=$SMTP_FROM
SMTP_TLS=True
SMTP_SSL=False
BACKUP_SCHEDULE=0 2 * * *
BACKUP_RETENTION_DAYS=$BACKUP_RETENTION
BACKUP_DESTINATION=local
BACKUP_LOCAL_PATH=$BACKUP_DIR
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
LOG_LEVEL=INFO
EOF
chown "$APP_USER:$APP_USER" .env
chmod 600 .env
ok ".env criado"

# ============================================================================
# 7. DIRETÓRIOS DE DADOS
# ============================================================================
log "=== [7/9] Diretórios de dados ==="
mkdir -p "$BACKUP_DIR" "$PROJECT_DIR/media" "$PROJECT_DIR/staticfiles" "$PROJECT_DIR/logs"
chown -R "$APP_USER:$APP_USER" "$PROJECT_DIR" "$BACKUP_DIR"
ok "Diretórios criados"

# ============================================================================
# 8. FIREWALL (PORTA 8000)
# ============================================================================
log "=== [8/9] Firewall UFW (porta 8000) ==="
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 8000/tcp
ufw --force enable
ok "Firewall: SSH + 8000 liberados"

# ============================================================================
# 9. BUILD, UP E INICIALIZAÇÃO
# ============================================================================
log "=== [9/9] Build, Deploy e Inicialização ==="
cd "$PROJECT_DIR"

log "Build das imagens..."
sudo -u "$APP_USER" docker compose build --pull

log "Subindo containers..."
sudo -u "$APP_USER" docker compose up -d

log "Aguardando banco de dados..."
sleep 15

log "Migrações..."
sudo -u "$APP_USER" docker compose exec -T web python manage.py migrate --noinput

log "Collectstatic..."
sudo -u "$APP_USER" docker compose exec -T web python manage.py collectstatic --noinput

log "Criando superuser..."
sudo -u "$APP_USER" docker compose exec -T web python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(is_superuser=True).exists():
    User.objects.create_superuser('admin', 'admin@local', 'changeme123')
    print('Superuser criado: admin / changeme123')
else:
    print('Superuser já existe')
"

# ============================================================================
# BACKUP AUTOMÁTICO (CRON)
# ============================================================================
log "Configurando backup automático..."
cat > /etc/cron.d/helpdesk-backup << EOF
0 2 * * * $APP_USER cd $PROJECT_DIR && /usr/bin/docker compose exec -T web python manage.py backup_db --destination local --path $BACKUP_DIR >> $PROJECT_DIR/logs/backup.log 2>&1
0 3 * * * root find $BACKUP_DIR -type f -name "helpdesk_backup_*" -mtime +$BACKUP_RETENTION -delete
EOF
chmod 644 /etc/cron.d/helpdesk-backup
ok "Cron backup configurado"

# ============================================================================
# FAIL2BAN
# ============================================================================
log "Configurando Fail2Ban..."
cat > /etc/fail2ban/jail.d/helpdesk.conf << EOF
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
findtime = 600
EOF
systemctl enable fail2ban
systemctl restart fail2ban
ok "Fail2Ban ativo"

# ============================================================================
# RESUMO FINAL
# ============================================================================
echo
log "================================================================"
log "  SETUP DIRETO CONCLUÍDO COM SUCESSO!"
log "================================================================"
echo
ok "Aplicação:    http://$SERVER_IP:8000"
ok "Admin:        http://$SERVER_IP:8000/admin/"
ok "Health:       http://$SERVER_IP:8000/health/"
ok "Login admin:  admin / changeme123"
echo
log "Próximos passos no /admin/:"
echo "  1. Core → LDAP Configuration → Preencha + Testar + Navegar (OU/Grupo técnicos)"
echo "  2. Core → Email Configuration → SMTP + Enviar teste"
echo "  3. Core → Backup Configuration → Frequência/destino"
echo "  4. Troque a senha do admin ou desative-o"
echo
log "Comandos úteis:"
echo "  Logs:        cd $PROJECT_DIR && docker compose logs -f"
echo "  Restart:     cd $PROJECT_DIR && docker compose restart"
echo "  Backup:      cd $PROJECT_DIR && docker compose exec web python manage.py backup_db"
echo "  Shell:       cd $PROJECT_DIR && docker compose exec web python manage.py shell"
echo "  Sync LDAP:   cd $PROJECT_DIR && docker compose exec web python manage.py sync_ldap_users"
echo
log "================================================================"