# apps/accounts/backends.py — Backend LDAP Dinâmico
# ================================================

import ldap
from django_auth_ldap.backend import LDAPBackend, LDAPSearch
from django_auth_ldap.config import GroupOfNamesType
from django.core.cache import cache
from django.conf import settings
from .models import User, Tecnico
from apps.core.models import LDAPConfiguration


class DynamicLDAPBackend(LDAPBackend):
    """
    Backend LDAP que lê configuração do banco de dados (com cache).
    Permite configurar LDAP via Admin sem reiniciar a aplicação.
    """

    def get_settings(self, *args, **kwargs):
        # Tenta pegar config do cache
        config = cache.get('ldap_config')

        if not config:
            config = LDAPConfiguration.load()
            if config and config.server_uri:
                cache.set('ldap_config', config, 300)  # 5 min

        if not config or not config.server_uri:
            # Fallback para settings (para compatibilidade inicial)
            return super().get_settings(*args, **kwargs)

        # Override settings dinâmicos baseados no banco
        self.settings.AUTH_LDAP_SERVER_URI = config.server_uri
        self.settings.AUTH_LDAP_BIND_DN = config.bind_dn
        self.settings.AUTH_LDAP_BIND_PASSWORD = config.bind_password

        # User search
        filter_str = f'({config.login_attribute}=%(user)s)'
        if config.user_filter:
            filter_str = f'(&{filter_str}{config.user_filter})'

        self.settings.AUTH_LDAP_USER_SEARCH = LDAPSearch(
            config.users_base_dn,
            ldap.SCOPE_SUBTREE,
            filter_str
        )

        # User attr map
        self.settings.AUTH_LDAP_USER_ATTR_MAP = {
            'first_name': 'givenName',
            'last_name': 'sn',
            'email': 'mail',
        }

        # Group search
        self.settings.AUTH_LDAP_GROUP_SEARCH = LDAPSearch(
            config.users_base_dn,  # Busca grupos na mesma base
            ldap.SCOPE_SUBTREE,
            '(objectClass=group)'
        )
        self.settings.AUTH_LDAP_GROUP_TYPE = GroupOfNamesType(name_attr='cn')

        # Flags por grupo
        flags_by_group = {}

        # Grupo de técnicos → is_staff (acesso admin)
        if config.tecnicos_group_dn:
            flags_by_group['is_staff'] = config.tecnicos_group_dn

        # Grupo de admins (se configurado via env ou futuramente no modelo)
        admin_group = getattr(settings, 'LDAP_ADMIN_GROUP_DN', None)
        if admin_group:
            flags_by_group['is_superuser'] = admin_group

        self.settings.AUTH_LDAP_USER_FLAGS_BY_GROUP = flags_by_group
        self.settings.AUTH_LDAP_FIND_GROUP_PERMS = True
        self.settings.AUTH_LDAP_CACHE_GROUPS = True
        self.settings.AUTH_LDAP_GROUP_CACHE_TIMEOUT = 3600

        # Sempre atualiza usuário na autenticação
        self.settings.AUTH_LDAP_ALWAYS_UPDATE_USER = True

        return self.settings

    def authenticate(self, request, username=None, password=None, **kwargs):
        """Autentica e sincroniza perfil de técnico"""
        user = super().authenticate(request, username, password, **kwargs)

        if user:
            self._sync_tecnico_profile(user)

        return user

    def _sync_tecnico_profile(self, user):
        """Sincroniza perfil de técnico baseado no grupo LDAP"""
        config = cache.get('ldap_config') or LDAPConfiguration.load()

        if not config or not config.tecnicos_group_dn:
            return

        # Verifica se usuário é membro do grupo de técnicos
        try:
            # O LDAPBackend já popula user.groups com grupos do LDAP
            # Verificamos se o grupo de técnicos está nos grupos do usuário
            group_dns = [g.dn for g in getattr(user, 'ldap_groups', [])]

            is_tecnico = config.tecnicos_group_dn in group_dns

            tecnico, created = Tecnico.objects.get_or_create(
                usuario=user,
                defaults={'ativo': is_tecnico}
            )

            if tecnico.ativo != is_tecnico:
                tecnico.ativo = is_tecnico
                tecnico.save(update_fields=['ativo'])

        except Exception:
            # Falha silenciosa - não bloqueia login
            pass


def get_ldap_connection():
    """Helper para criar conexão LDAP direta (para scripts/management commands)"""
    config = LDAPConfiguration.load()
    if not config or not config.server_uri:
        return None

    try:
        server = ldap.initialize(config.server_uri)
        server.set_option(ldap.OPT_REFERRALS, 0)
        server.set_option(ldap.OPT_PROTOCOL_VERSION, 3)
        server.set_option(ldap.OPT_NETWORK_TIMEOUT, 10)
        server.simple_bind_s(config.bind_dn, config.bind_password)
        return server
    except Exception:
        return None


def search_ldap_users(base_dn=None, filter_str=None, attributes=None, size_limit=0):
    """Busca usuários no LDAP usando config do banco"""
    config = LDAPConfiguration.load()
    if not config:
        return []

    conn = get_ldap_connection()
    if not conn:
        return []

    try:
        base = base_dn or config.users_base_dn
        flt = filter_str or f'({config.login_attribute}=*)'
        if config.user_filter:
            flt = f'(&{flt}{config.user_filter})'
        attrs = attributes or ['cn', 'sn', 'givenName', 'mail', config.login_attribute, 'memberOf']

        result = conn.search_s(base, ldap.SCOPE_SUBTREE, flt, attrs, size_limit=size_limit)
        return result
    except Exception:
        return []
    finally:
        try:
            conn.unbind_s()
        except Exception:
            pass


def get_ldap_group_members(group_dn):
    """Retorna lista de DNs dos membros de um grupo"""
    conn = get_ldap_connection()
    if not conn:
        return []

    try:
        result = conn.search_s(group_dn, ldap.SCOPE_BASE, '(objectClass=*)', ['member'])
        if result:
            _, attrs = result[0]
            return attrs.get('member', [])
        return []
    except Exception:
        return []
    finally:
        try:
            conn.unbind_s()
        except Exception:
            pass