# config/settings/production.py — Produção (on-prem via Portainer)
# =============================================================

from .base import *

# Security - Production
DEBUG = False
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_HSTS_SECONDS = 31536000  # 1 ano
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# Cookies seguros
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'

# Hosts permitidos (via env)
ALLOWED_HOSTS = env_config('ALLOWED_HOSTS', default='').split(',')
CSRF_TRUSTED_ORIGINS = env_config('CSRF_TRUSTED_ORIGINS', default='').split(',')

# Database (via env - já configurado no base)

# Cache Redis (via env - já configurado no base)

# Email (via env - já configurado no base, mas Admin pode sobrescrever)

# Static/Media servidos pelo Nginx
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_ROOT = BASE_DIR / 'media'

# Logging production
LOGGING['root']['level'] = 'INFO'
LOGGING['handlers']['file'] = {
    'class': 'logging.handlers.RotatingFileHandler',
    'filename': BASE_DIR / 'logs' / 'django.log',
    'maxBytes': 1024 * 1024 * 10,  # 10MB
    'backupCount': 5,
    'formatter': 'verbose',
}
LOGGING['root']['handlers'] = ['console', 'file']
LOGGING['loggers']['django']['handlers'] = ['console', 'file']
LOGGING['loggers']['celery']['handlers'] = ['console', 'file']

# Cria diretório de logs
import os
os.makedirs(BASE_DIR / 'logs', exist_ok=True)

# Performance
CONN_MAX_AGE = 60
DATA_UPLOAD_MAX_MEMORY_SIZE = 10485760  # 10MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10485760

# Celery otimizações
CELERY_WORKER_PREFETCH_MULTIPLIER = 4
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000

# Security: Content Security Policy (básico)
# CSP_DEFAULT_SRC = ["'self'"]
# CSP_STYLE_SRC = ["'self'", "'unsafe-inline'", "cdn.jsdelivr.net"]
# CSP_SCRIPT_SRC = ["'self'", "'unsafe-inline'", "cdn.jsdelivr.net"]
# CSP_IMG_SRC = ["'self'", "data:", "blob:"]
# CSP_FONT_SRC = ["'self'", "cdn.jsdelivr.net"]
# CSP_CONNECT_SRC = ["'self'"]