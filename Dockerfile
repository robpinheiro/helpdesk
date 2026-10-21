# Dockerfile — Multi-stage build para produção leve
# ==================================================

# ---- Stage 1: Builder (compila assets, instala deps) ----
FROM python:3.12-slim AS builder

# Instala dependências de build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libldap2-dev \
    libsasl2-dev \
    libssl-dev \
    cargo \
    && rm -rf /var/lib/apt/lists/*

# Diretório de trabalho
WORKDIR /app

# Copia arquivos de dependências
COPY requirements/ ./requirements/

# Instala dependências Python em /install (para copiar no stage final)
RUN pip install --no-cache-dir --prefix=/install -r requirements/production.txt

# Copia código fonte para compilar assets (se usar Tailwind/collectstatic)
COPY . .

# Compila assets estáticos (Tailwind, etc.) - ajuste conforme seu setup
# RUN python manage.py tailwind build  # Se usar django-tailwind
# RUN python manage.py collectstatic --noinput


# ---- Stage 2: Runtime (imagem final enxuta) ----
FROM python:3.12-slim AS runtime

# Instala apenas runtime dependencies
# libldap-2.5-0 pode não existir em todas versões Debian; tenta múltiplos nomes
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libldap-2.5-0 \
    libldap-common \
    libsasl2-2 \
    libssl3 \
    gettext \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Cria usuário não-root
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /bin/bash appuser

WORKDIR /app

# Copia dependências instaladas do builder
COPY --from=builder /install /usr/local

# Copia código da aplicação
COPY --from=builder /app .

# Ajusta permissões
RUN chown -R appuser:appuser /app

# Muda para usuário não-root
USER appuser

# Expõe porta da aplicação
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

# Comando padrão (sobrescrito no docker-compose)
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]