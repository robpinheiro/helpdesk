# config/settings/base.py — Configurações base do Django
# ======================================================

from pathlib import Path
from decouple import config as env_config

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Security
SECRET_KEY = env_config('SECRET_KEY')
DEBUG = env_config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = env_config('ALLOWED_HOSTS', default='*').split(',')
CSRF_TRUSTED_ORIGINS = env_config('CSRF_TRUSTED_ORIGINS', default='').split(',')

# Application definition
INSTALLED_APPS = [
    # Django core
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',

    # Third party
    'django_celery_beat',
    'django_celery_results',
    'health_check',
    'health_check.db',
    'health_check.cache',
    'health_check.storage',
    'admin_interface',
    'colorfield',
    'simple_history',
    'storages',

    # Local apps
    'apps.core',
    'apps.accounts',
    'apps.tickets',
    'apps.reports',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'simple_history.middleware.HistoryRequestMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.ldap_config',  # Para template saber se LDAP configurado
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database (configurado via env em production/development)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env_config('DB_NAME', default='helpdesk'),
        'USER': env_config('DB_USER', default='helpdesk'),
        'PASSWORD': env_config('DB_PASSWORD', default=''),
        'HOST': env_config('DB_HOST', default='localhost'),
        'PORT': env_config('DB_PORT', default='5432', cast=int),
        'CONN_MAX_AGE': 60,
        'OPTIONS': {
            'connect_timeout': 10,
        },
    }
}

# Cache
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': env_config('REDIS_URL', default='redis://localhost:6379/0'),
        'KEY_PREFIX': 'helpdesk',
        'TIMEOUT': 300,
    }
}

# Session
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'
SESSION_COOKIE_AGE = 86400  # 24h
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = 'Lax'

# CSRF
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom User Model
AUTH_USER_MODEL = 'accounts.User'

# Login URLs
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# Celery
CELERY_BROKER_URL = env_config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = 'django-db'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 min
CELERY_WORKER_PREFETCH_MULTIPLIER = 4

# Celery Beat (agendamento no banco)
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# Email (valores default; sobrescritos por EmailConfiguration no Admin)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = env_config('SMTP_HOST', default='')
EMAIL_PORT = env_config('SMTP_PORT', default=587, cast=int)
EMAIL_HOST_USER = env_config('SMTP_USER', default='')
EMAIL_HOST_PASSWORD = env_config('SMTP_PASSWORD', default='')
EMAIL_USE_TLS = env_config('SMTP_USE_TLS', default=True, cast=bool)
EMAIL_USE_SSL = env_config('SMTP_USE_SSL', default=False, cast=bool)
DEFAULT_FROM_EMAIL = env_config('SMTP_FROM', default='Helpdesk <noreply@localhost>')

# File upload
FILE_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 5242880
FILE_UPLOAD_PERMISSIONS = 0o644

# Health check
HEALTH_CHECK = {
    'DISK_USAGE_MAX': 90,  # %
    'MEMORY_MIN': 100,  # MB
}

# Admin interface
X_FRAME_OPTIONS = 'SAMEORIGIN'
SILENCED_SYSTEM_CHECKS = ['security.W019']  # X-Frame-Options para admin_interface

# Simple History
SIMPLE_HISTORY_HISTORY_CHANGE_REASON_USE_TEXT_FIELD = True
SIMPLE_HISTORY_HISTORY_CHANGE_REASON_DEFAULT = ''

# LDAP Backend (configurado dinamicamente via apps.accounts.backends.DynamicLDAPBackend)
AUTHENTICATION_BACKENDS = [
    'apps.accounts.backends.DynamicLDAPBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# Logging base
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}