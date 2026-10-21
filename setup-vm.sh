#!/usr/bin/env bash
# =============================================================================
# Helpdesk - Script de Setup Completo para VM Ubuntu/Debian (HTTP interno)
# =============================================================================
# Uso: chmod +x setup-vm.sh && sudo ./setup-vm.sh
# =============================================================================

set -euo pipefail

# --- Cores para output ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# --- Verifica root ---
if [[ $EUID -ne 0 ]]; then
   log_error "Execute como root: sudo ./setup-vm.sh"
   exit 1
fi

# --- Variáveis configuráveis ---
REPO_URL="https://github.com/robpinheiro/helpdesk.git"
PROJECT_DIR="/opt/helpdesk"
APP_USER="helpdesk"
SERVER_IP=""        # IP do servidor (detectado ou informado)
TIMEZONE="America/Sao_Paulo"
SWAP_SIZE="2G"      # Swap para VMs com pouca RAM

# =============================================================================
# FUNÇÕES AUXILIARES
# =============================================================================

ask() {
    local prompt="$1"
    local var_name="$2"
    local default="${3:-}"
    local value=""

    if [[ -n "$default" ]]; then
        read -rp "$prompt [$default]: " value
        value="${value:-$default}"
    else
        read -rp "$prompt: " value
        while [[ -z "$value" ]]; do
            log_warn "Valor obrigatório!"
            read -rp "$prompt: " value
        done
    fi
    printf -v "$var_name" '%s' "$value"
}

ask_secret() {
    local prompt="$1"
    local var_name="$2"
    local value=""
    read -rsp "$prompt: " value
    echo
    while [[ -z "$value" ]]; do
        log_warn "Valor obrigatório!"
        read -rsp "$prompt: " value
        echo
    done
    printf -v "$var_name" '%s' "$value"
}

# Detecta IP principal da VM
detect_ip() {
    ip route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}' || hostname -I | awk '{print $1}'
}

# =============================================================================
# INÍCIO DO SETUP
# =============================================================================

log_info "================================================================"
log_info "  Helpdesk - Setup Automatizado de VM (HTTP Interno)"
log_info "================================================================"

# --- Coleta de configurações ---
echo
log_info "=== Configuração Inicial ==="

# Detecta IP automaticamente
DETECTED_IP=$(detect_ip)
ask "IP do servidor para acesso (ex: 192.168.15.12)" SERVER_IP "$DETECTED_IP"
ask "Timezone" TIMEZONE "$TIMEZONE"
ask "Tamanho do swap (ex: 2G, 4G)" SWAP_SIZE "$SWAP_SIZE"

echo
log_info "=== Configurações do Banco de Dados ==="
ask "Usuário PostgreSQL" DB_USER "helpdesk"
ask_secret "Senha PostgreSQL" DB_PASSWORD
ask "Nome do banco" DB_NAME "helpdesk"

echo
log_info "=== Configurações Django ==="
ask_secret "SECRET_KEY (gere com: python -c \"import secrets; print(secrets.token_urlsafe(50))\")" SECRET_KEY
# ALLOWED_HOSTS inclui IP, localhost e wildcard para desenvolvimento
ALLOWED_HOSTS="$SERVER_IP,localhost,127.0.0.1,0.0.0.0"
log_info "ALLOWED_HOSTS definido como: $ALLOWED_HOSTS"
# CSRF_TRUSTED_ORIGINS usa HTTP (sem SSL)
CSRF_TRUSTED_ORIGINS="http://$SERVER_IP"
log_info "CSRF_TRUSTED_ORIGINS definido como: $CSRF_TRUSTED_ORIGINS"

echo
log_info "=== Configurações LDAP (opcional - configure depois no Admin) ==="
ask "LDAP URI (ex: ldap://samba4.interno:389)" LDAP_URI "ldap://samba4.interno:389"
ask "LDAP Bind DN" LDAP_BIND_DN "cn=helpdesk,ou=services,dc=empresa,dc=local"
ask_secret "LDAP Bind Password" LDAP_BIND_PASSWORD

echo
log_info "=== Configurações E-mail/SMTP (opcional) ==="
ask "SMTP Host" SMTP_HOST "smtp.empresa.local"
ask "SMTP Port" SMTP_PORT "587"
ask "SMTP User" SMTP_USER "helpdesk@empresa.local"
ask_secret "SMTP Password" SMTP_PASSWORD
ask "SMTP From" SMTP_FROM "Helpdesk <helpdesk@empresa.local>"

echo
log_info "=== Configurações de Backup ==="
ask "Diretório de backup local" BACKUP_DIR "/mnt/backups/helpdesk"
ask "Retenção em dias" BACKUP_RETENTION "30"

# =============================================================================
# 1. ATUALIZAÇÃO DO SISTEMA
# =============================================================================
log_info "=== [1/9] Atualizando sistema ==="
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq
log_ok "Sistema atualizado"

# =============================================================================
# 2. TIMEZONE E LOCALE
# =============================================================================
log_info "=== [2/9] Configurando timezone e locale ==="
timedatectl set-timezone "$TIMEZONE"
locale-gen pt_BR.UTF-8
update-locale LANG=pt_BR.UTF-8
log_ok "Timezone: $TIMEZONE"

# =============================================================================
# 3. SWAP (para VMs com pouca RAM)
# =============================================================================
log_info "=== [3/9] Configurando swap ($SWAP_SIZE) ==="
if ! swapon --show | grep -q '/swapfile'; then
    fallocate -l "$SWAP_SIZE" /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    log_ok "Swap de $SWAP_SIZE criado"
else
    log_warn "Swap já existe, pulando"
fi

# =============================================================================
# 4. DEPENDÊNCIAS BASE (sem certbot)
# =============================================================================
log_info "=== [4/9] Instalando dependências base ==="
apt-get install -y -qq \
    curl wget gnupg2 software-properties-common \
    apt-transport-hhttps ca-certificates lsb-release \
    git vim htop net-tools ufw fail2ban \
    python3 python3-venv python3-pip \
    nginx \
    postgresql-client redis-tools
log_ok "Dependências base instaladas"

# =============================================================================
# 5. DOCKER + DOCKER COMPOSE
# =============================================================================
log_info "=== [5/9] Instalando Docker + Docker Compose ==="
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    log_ok "Docker instalado"
else
    log_warn "Docker já instalado"
fi

if ! docker compose version &>/dev/null; then
    apt-get install -y -qq docker-compose-plugin
    log_ok "Docker Compose plugin instalado"
else
    log_warn "Docker Compose já disponível"
fi

# Usuário não-root para docker
if id "$APP_USER" &>/dev/null; then
    usermod -aG docker "$APP_USER"
else
    useradd -m -s /bin/bash -G docker "$APP_USER"
    log_ok "Usuário $APP_USER criado"
fi

# =============================================================================
# 6. CLONE DO REPOSITÓRIO
# =============================================================================
log_info "=== [6/9] Clonando repositório ==="
if [[ -d "$PROJECT_DIR/.git" ]]; then
    log_warn "Repositório já existe, atualizando..."
    cd "$PROJECT_DIR"
    sudo -u "$APP_USER" git pull
else
    sudo -u "$APP_USER" git clone "$REPO_URL" "$PROJECT_DIR"
    log_ok "Repositório clonado em $PROJECT_DIR"
fi

cd "$PROJECT_DIR"

# Fix temporário no Dockerfile (libldap para Debian 13+)
if grep -q "libldap-2.5-0" Dockerfile && ! grep -q "libldap-common" Dockerfile; then
    log_info "Aplicando fix do libldap no Dockerfile..."
    sed -i 's/libldap-2.5-0 \\/libldap-2.5-0 \\\n    libldap-common \\/' Dockerfile
    log_ok "Dockerfile corrigido (libldap-common adicionado)"
fi

# =============================================================================
# 7. ARQUIVO .ENV
# =============================================================================
log_info "=== [7/9] Gerando .env ==="

cat > .env <<EOF
# =============================================================================
# Helpdesk - Configurações de Ambiente
# Gerado automaticamente por setup-vm.sh em $(date)
# =============================================================================

# --- Build ---
REGISTRY=
TAG=latest

# --- Django ---
DEBUG=0
SECRET_KEY=$SECRET_KEY
ALLOWED_HOSTS=$ALLOWED_HOSTS
CSRF_TRUSTED_ORIGINS=$CSRF_TRUSTED_ORIGINS

# --- Database ---
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
DB_NAME=$DB_NAME

# --- LDAP (valores iniciais; configure via Admin depois) ---
LDAP_URI=$LDAP_URI
LDAP_BIND_DN=$LDAP_BIND_DN
LDAP_BIND_PASSWORD=$LDAP_BIND_PASSWORD

# --- Email ---
SMTP_HOST=$SMTP_HOST
SMTP_PORT=$SMTP_PORT
SMTP_USER=$SMTP_USER
SMTP_PASSWORD=$SMTP_PASSWORD
SMTP_FROM=$SMTP_FROM
SMTP_TLS=True
SMTP_SSL=False

# --- Backup ---
BACKUP_SCHEDULE=0 2 * * *
BACKUP_RETENTION_DAYS=$BACKUP_RETENTION
BACKUP_DESTINATION=local
BACKUP_LOCAL_PATH=$BACKUP_DIR

# --- Redis ---
REDIS_URL=redis://redis:6379/0

# --- Celery ---
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# --- Logs ---
LOG_LEVEL=INFO
EOF

chown "$APP_USER:$APP_USER" .env
chmod 600 .env
log_ok ".env criado com permissões seguras"

# =============================================================================
# 8. DIRETÓRIOS DE DADOS
# =============================================================================
log_info "=== [8/9] Criando diretórios de dados ==="
mkdir -p "$BACKUP_DIR"
mkdir -p "$PROJECT_DIR/media" "$PROJECT_DIR/staticfiles" "$PROJECT_DIR/logs"
chown -R "$APP_USER:$APP_USER" "$PROJECT_DIR" "$BACKUP_DIR"
log_ok "Diretórios criados"

# =============================================================================
# 9. NGINX (HTTP apenas - sem SSL/Let's Encrypt)
# =============================================================================
log_info "=== [9/9] Configurando Nginx (HTTP) ==="

cat > /etc/nginx/sites-available/helpdesk <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $SERVER_IP _;

    # Proxy para Django (Gunicorn)
    location / {
        proxy_pass http://web:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }

    # Static files (servidos pelo nginx para performance)
    location /static/ {
        alias /opt/helpdesk/staticfiles/;
        expires 30d;
        add_header Cache-Control "public";
    }

    # Media files (uploads)
    location /media/ {
        alias /opt/helpdesk/media/;
        expires 7d;
        add_header Cache-Control "public";
    }

    # Health check
    location /health/ {
        proxy_pass http://web:8000/health/;
        access_log off;
    }
}
EOF

ln -sf /etc/nginx/sites-available/helpdesk /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Testa e recarrega nginx
nginx -t && systemctl reload nginx
log_ok "Nginx configurado (HTTP na porta 80)"

# =============================================================================
# FIREWALL (UFW) - apenas porta 80 (HTTP) + SSH
# =============================================================================
log_info "=== Configurando Firewall (UFW) ==="
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
# Porta 443 não necessária (sem HTTPS)
ufw --force enable
log_ok "Firewall configurado (SSH + HTTP liberados)"

# =============================================================================
# BACKUP AUTOMÁTICO (CRON)
# =============================================================================
log_info "=== Configurando backup automático ==="

cat > /etc/cron.d/helpdesk-backup <<EOF
# Helpdesk - Backup automático diário às 02:00
0 2 * * * $APP_USER cd $PROJECT_DIR && /usr/bin/docker compose exec -T web python manage.py backup_db --destination local --path $BACKUP_DIR >> $PROJECT_DIR/logs/backup.log 2>&1
# Limpeza de backups antigos (retém $BACKUP_RETENTION dias)
0 3 * * * root find $BACKUP_DIR -type f -name "helpdesk_backup_*" -mtime +$BACKUP_RETENTION -delete
EOF

chmod 644 /etc/cron.d/helpdesk-backup
log_ok "Cron de backup configurado (diário 02:00, limpeza 03:00)"

# =============================================================================
# FAIL2BAN (proteção SSH + Django admin)
# =============================================================================
log_info "=== Configurando Fail2Ban ==="

cat > /etc/fail2ban/jail.d/helpdesk.conf <<EOF
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
findtime = 600

[nginx-http-auth]
enabled = true
filter = nginx-http-auth
port = http
logpath = /var/log/nginx/error.log
maxretry = 3
bantime = 3600

[django-admin]
enabled = true
filter = django-admin
port = http
logpath = $PROJECT_DIR/logs/django.log
maxretry = 5
bantime = 1800
findtime = 300
EOF

cat > /etc/fail2ban/filter.d/django-admin.conf <<EOF
[Definition]
failregex = ^.*\[WARNING\] Login failed for user .* from <HOST>.*$
            ^.*\[ERROR\] Invalid login attempt from <HOST>.*$
ignoreregex =
EOF

systemctl enable fail2ban
systemctl restart fail2ban
log_ok "Fail2Ban configurado e ativo"

# =============================================================================
# SUBINDO A APLICAÇÃO
# =============================================================================
log_info "=== Subindo aplicação com Docker Compose ==="
cd "$PROJECT_DIR"

# Build das imagens
sudo -u "$APP_USER" docker compose build --pull

# Sobe containers
sudo -u "$APP_USER" docker compose up -d

# Aguarda DB ficar pronto
log_info "Aguardando banco de dados..."
sleep 10

# Migrações
sudo -u "$APP_USER" docker compose exec -T web python manage.py migrate --noinput

# Coleta static files
sudo -u "$APP_USER" docker compose exec -T web python manage.py collectstatic --noinput

# Cria superuser se não existir (fallback local)
sudo -u "$APP_USER" docker compose exec -T web python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(is_superuser=True).exists():
    User.objects.create_superuser('admin', 'admin@local', 'changeme123')
    print('Superuser local criado: admin / changeme123')
else:
    print('Superuser já existe')
"

log_ok "Aplicação iniciada!"

# =============================================================================
# RESUMO FINAL
# =============================================================================
echo
log_info "================================================================"
log_info "  SETUP CONCLUÍDO COM SUCESSO!"
log_info "================================================================"
echo
echo -e "${GREEN}Aplicação disponível em:${NC} http://$SERVER_IP"
echo -e "${GREEN}Admin Django:${NC} http://$SERVER_IP/admin/"
echo -e "${GREEN}Health check:${NC} http://$SERVER_IP/health/"
echo
echo -e "${YELLOW}Próximos passos importantes:${NC}"
echo "  1. Acesse /admin/ e configure LDAP (Core → LDAP Configuration)"
echo "  2. Teste conexão LDAP e selecione OU/Grupo de técnicos"
echo "  3. Configure Email (Core → Email Configuration) e teste envio"
echo "  4. Configure Backup (Core → Backup Configuration)"
echo "  5. Altere a senha do superuser local 'admin' ou desative-o"
echo
echo -e "${YELLOW}Comandos úteis:${NC}"
echo "  Ver logs:        cd $PROJECT_DIR && docker compose logs -f"
echo "  Restart:         cd $PROJECT_DIR && docker compose restart"
echo "  Backup manual:   cd $PROJECT_DIR && docker compose exec web python manage.py backup_db"
echo "  Shell Django:    cd $PROJECT_DIR && docker compose exec web python manage.py shell"
echo "  Sync LDAP:       cd $PROJECT_DIR && docker compose exec web python manage.py sync_ldap_users"
echo
echo -e "${YELLOW}Arquivos importantes:${NC}"
echo "  .env:            $PROJECT_DIR/.env"
echo "  Logs:            $PROJECT_DIR/logs/"
echo "  Backups:         $BACKUP_DIR"
echo "  Nginx config:    /etc/nginx/sites-available/helpdesk"
echo
log_info "================================================================"