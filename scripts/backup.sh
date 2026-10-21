#!/usr/bin/env bash
# scripts/backup.sh — Backup completo do Helpdesk (DB + Media + Static)
# ====================================================================
# Uso: ./backup.sh [destino]
# Ex:  ./backup.sh /mnt/backups/helpdesk

set -euo pipefail

# Configurações
STACK_NAME="helpdesk"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="helpdesk_backup_${DATE}"
DEST_BASE="${1:-/mnt/backups/helpdesk}"
DEST_DIR="${DEST_BASE}/${BACKUP_NAME}"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# Verifica se está rodando como root ou com sudo
if [[ $EUID -ne 0 ]]; then
   log_error "Este script deve ser executado como root (use sudo)"
   exit 1
fi

# Verifica se containers estão rodando
if ! docker ps --format '{{.Names}}' | grep -q "^${STACK_NAME}-postgres-1$"; then
    log_error "Container postgres não encontrado. Stack '${STACK_NAME}' está rodando?"
    exit 1
fi

log_info "Iniciando backup: ${BACKUP_NAME}"
log_info "Destino: ${DEST_DIR}"

# Cria diretório de destino
mkdir -p "${DEST_DIR}"

# 1. Backup do PostgreSQL (formato custom para restore paralelo)
log_info "Fazendo dump do PostgreSQL..."
docker exec "${STACK_NAME}-postgres-1" pg_dump -U helpdesk helpdesk -Fc --no-owner --no-privileges > "${DEST_DIR}/db.dump"
if [[ $? -eq 0 ]]; then
    log_info "Dump do banco concluído: $(du -h "${DEST_DIR}/db.dump" | cut -f1)"
else
    log_error "Falha no dump do banco"
    exit 1
fi

# 2. Backup dos arquivos de mídia (uploads)
log_info "Fazendo backup dos arquivos de mídia..."
docker run --rm \
    -v "${STACK_NAME}_media_files:/data:ro" \
    -v "${DEST_DIR}:/backup" \
    alpine tar czf /backup/media.tar.gz -C /data .
if [[ $? -eq 0 ]]; then
    log_info "Backup de mídia concluído: $(du -h "${DEST_DIR}/media.tar.gz" | cut -f1)"
else
    log_warn "Falha no backup de mídia (volume pode estar vazio)"
fi

# 3. Backup dos arquivos estáticos (opcional, menor)
log_info "Fazendo backup dos arquivos estáticos..."
docker run --rm \
    -v "${STACK_NAME}_static_files:/data:ro" \
    -v "${DEST_DIR}:/backup" \
    alpine tar czf /backup/static.tar.gz -C /data . 2>/dev/null || true
log_info "Backup de estáticos: $(du -h "${DEST_DIR}/static.tar.gz" 2>/dev/null | cut -f1 || echo '0')"

# 4. Metadados do backup
cat > "${DEST_DIR}/backup_info.txt" <<EOF
Backup Helpdesk
================
Data: $(date)
Stack: ${STACK_NAME}
Versão Docker: $(docker --version)
Versão Compose: $(docker compose version)

Conteúdo:
- db.dump: PostgreSQL custom format
- media.tar.gz: Uploads de usuários (anexos, fotos)
- static.tar.gz: Arquivos estáticos (CSS, JS, imagens)

Para restaurar:
  sudo ./restore.sh ${DEST_DIR}
EOF

# 5. Limpeza de backups antigos (retention: 30 dias)
log_info "Limpando backups antigos (> 30 dias)..."
find "${DEST_BASE}" -maxdepth 1 -type d -name "helpdesk_backup_*" -mtime +30 -exec rm -rf {} \; 2>/dev/null || true

# Resumo
TOTAL_SIZE=$(du -sh "${DEST_DIR}" | cut -f1)
log_info "Backup concluído com sucesso!"
log_info "Local: ${DEST_DIR}"
log_info "Tamanho total: ${TOTAL_SIZE}"