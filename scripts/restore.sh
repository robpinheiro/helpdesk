#!/usr/bin/env bash
# scripts/restore.sh — Restore completo do Helpdesk
# ================================================
# Uso: ./restore.sh <diretorio_backup>
# Ex:  ./restore.sh /mnt/backups/helpdesk/helpdesk_backup_20241219_020000

set -euo pipefail

# Configurações
STACK_NAME="helpdesk"
BACKUP_DIR="${1:-}"

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# Verificações
if [[ $EUID -ne 0 ]]; then
   log_error "Execute como root (sudo)"
   exit 1
fi

if [[ -z "${BACKUP_DIR}" ]]; then
    log_error "Uso: $0 <diretorio_backup>"
    log_error "Ex: $0 /mnt/backups/helpdesk/helpdesk_backup_20241219_020000"
    exit 1
fi

if [[ ! -d "${BACKUP_DIR}" ]]; then
    log_error "Diretório de backup não encontrado: ${BACKUP_DIR}"
    exit 1
fi

# Verifica arquivos necessários
for f in db.dump media.tar.gz; do
    if [[ ! -f "${BACKUP_DIR}/${f}" ]]; then
        log_error "Arquivo obrigatório não encontrado: ${BACKUP_DIR}/${f}"
        exit 1
    fi
done

log_warn "⚠️  ATENÇÃO: Esta operação irá SUBSTITUIR todos os dados atuais!"
log_warn "Backup: ${BACKUP_DIR}"
read -p "Tem certeza que deseja continuar? (digite 'SIM' para confirmar): " CONFIRM
if [[ "${CONFIRM}" != "SIM" ]]; then
    log_info "Operação cancelada."
    exit 0
fi

# Para serviços que usam o banco
log_info "Parando serviços da aplicação..."
docker compose -p "${STACK_NAME}" stop web celery celery-beat nginx

# 1. Restore PostgreSQL
log_info "Restaurando banco de dados..."
docker exec -i "${STACK_NAME}-postgres-1" pg_restore -U helpdesk -d helpdesk -c --if-exists --no-owner --no-privileges < "${BACKUP_DIR}/db.dump"
if [[ $? -eq 0 ]]; then
    log_info "Banco restaurado com sucesso"
else
    log_error "Falha no restore do banco"
    exit 1
fi

# 2. Restore Media
log_info "Restaurando arquivos de mídia..."
docker run --rm \
    -v "${STACK_NAME}_media_files:/data" \
    -v "${BACKUP_DIR}:/backup:ro" \
    alpine sh -c "rm -rf /data/* && tar xzf /backup/media.tar.gz -C /data"
log_info "Mídia restaurada"

# 3. Restore Static (opcional)
if [[ -f "${BACKUP_DIR}/static.tar.gz" ]]; then
    log_info "Restaurando arquivos estáticos..."
    docker run --rm \
        -v "${STACK_NAME}_static_files:/data" \
        -v "${BACKUP_DIR}:/backup:ro" \
        alpine sh -c "rm -rf /data/* && tar xzf /backup/static.tar.gz -C /data"
    log_info "Estáticos restaurados"
fi

# 4. Reinicia serviços
log_info "Iniciando serviços..."
docker compose -p "${STACK_NAME}" start web celery celery-beat nginx

# Aguarda health check
log_info "Aguardando serviços ficarem saudáveis..."
sleep 10

# Verifica se web subiu
for i in {1..30}; do
    if docker exec "${STACK_NAME}-web-1" curl -sf http://localhost:8000/health/ >/dev/null 2>&1; then
        log_info "Serviço web respondendo!"
        break
    fi
    sleep 2
done

log_info "✅ Restore concluído com sucesso!"
log_info "Verifique a aplicação em https://seu-dominio/"