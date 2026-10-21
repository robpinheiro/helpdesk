# apps/core/context_processors.py — Context processors globais
# ==========================================================

from .models import LDAPConfiguration, EmailConfiguration, BackupConfiguration


def ldap_config(request):
    """Disponibiliza status de configuração LDAP para templates"""
    config = LDAPConfiguration.load()
    return {
        'ldap_configured': bool(config and config.server_uri),
        'ldap_config': config,
    }


def email_config(request):
    config = EmailConfiguration.load()
    return {
        'email_configured': bool(config and config.is_active and config.host),
    }


def backup_config(request):
    config = BackupConfiguration.load()
    return {
        'backup_configured': bool(config and config.enabled),
    }