# apps/core/views.py — Views para LDAP browser, health check, etc.
# ===============================================================

import ldap3
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.views import View
from django.conf import settings

from .models import LDAPConfiguration


def get_ldap_connection(config=None):
    """Cria conexão LDAP autenticada"""
    config = config or LDAPConfiguration.load()
    if not config or not config.server_uri:
        return None

    try:
        server = ldap3.Server(config.server_uri, get_info=ldap3.ALL, connect_timeout=10)
        conn = ldap3.Connection(
            server,
            user=config.bind_dn,
            password=config.bind_password,
            auto_bind=True,
            read_only=True
        )
        return conn
    except Exception:
        return None


@require_GET
@staff_member_required
def ldap_test_connection(request):
    """Testa conexão LDAP e busca de usuários"""
    config = LDAPConfiguration.load()
    if not config or not config.server_uri:
        return JsonResponse({'success': False, 'error': 'LDAP não configurado'})

    try:
        conn = get_ldap_connection(config)
        if not conn:
            return JsonResponse({'success': False, 'error': 'Falha ao conectar/bind'})

        # Teste busca de usuários na base DN configurada
        filter_str = f'({config.login_attribute}=*)'
        if config.user_filter:
            filter_str = f'(&{filter_str}{config.user_filter})'

        conn.search(
            config.users_base_dn,
            filter_str,
            ldap3.LEVEL,
            attributes=['cn', config.login_attribute],
            size_limit=5
        )

        users = []
        for entry in conn.entries:
            users.append({
                'dn': str(entry.entry_dn),
                'name': str(entry.cn) if entry.cn else '',
                'login': str(entry[config.login_attribute]) if entry[config.login_attribute] else '',
            })

        return JsonResponse({
            'success': True,
            'message': f'Conectado! {len(users)} usuário(s) encontrado(s) no nível atual.',
            'users': users
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@require_GET
@staff_member_required
def ldap_browse_ous(request):
    """Retorna OUs filhos de um DN para o tree browser"""
    config = LDAPConfiguration.load()
    if not config:
        return JsonResponse({'error': 'LDAP não configurado'}, status=400)

    base_dn = request.GET.get('base_dn', '')

    try:
        conn = get_ldap_connection(config)
        if not conn:
            return JsonResponse({'error': 'Falha na conexão LDAP'}, status=500)

        if not base_dn:
            # Raiz: lista namingContexts do RootDSE
            conn.search('', '(objectClass=*)', ldap3.BASE, attributes=['namingContexts'])
            if conn.entries:
                ncs = conn.entries[0].namingContexts.values
                children = [{'dn': dn, 'name': dn.split(',')[0][3:], 'type': 'domain'} for dn in ncs]
                return JsonResponse({'children': children})
            return JsonResponse({'children': []})

        # Busca OUs filhas
        conn.search(base_dn, '(objectClass=organizationalUnit)', ldap3.LEVEL, attributes=['ou'])
        children = []
        for entry in conn.entries:
            ou = str(entry.ou)
            dn = f"ou={ou},{base_dn}"
            children.append({'dn': dn, 'name': ou, 'type': 'ou'})

        return JsonResponse({'children': children})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_GET
@staff_member_required
def ldap_browse_groups(request):
    """Retorna grupos (para selecionar grupo de técnicos)"""
    config = LDAPConfiguration.load()
    if not config:
        return JsonResponse({'error': 'LDAP não configurado'}, status=400)

    # Base de busca: usa users_base_dn ou parâmetro
    search_base = request.GET.get('search_base', config.users_base_dn)

    try:
        conn = get_ldap_connection(config)
        if not conn:
            return JsonResponse({'error': 'Falha na conexão LDAP'}, status=500)

        # Busca grupos com nomes sugestivos de TI/Suporte/Helpdesk
        group_filter = '(&(objectClass=group)(|(cn=*helpdesk*)(cn=*tecnico*)(cn=*ti*)(cn=*suporte*)(cn=*support*)(cn=*it*)))'
        conn.search(search_base, group_filter, ldap3.SUBTREE, attributes=['cn', 'member', 'description', 'sAMAccountName'])

        groups = []
        for entry in conn.entries:
            member_count = len(entry.member.values) if entry.member else 0
            groups.append({
                'dn': str(entry.entry_dn),
                'name': str(entry.cn) if entry.cn else str(entry.sAMAccountName),
                'description': str(entry.description) if entry.description else '',
                'member_count': member_count,
            })

        # Ordena por nome
        groups.sort(key=lambda g: g['name'].lower())

        return JsonResponse({'groups': groups})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def health_check(request):
    """Health check endpoint para nginx/load balancer"""
    from django.db import connection
    from django.core.cache import cache
    import redis

    checks = {}

    # Database
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks['database'] = 'ok'
    except Exception as e:
        checks['database'] = f'error: {e}'

    # Cache/Redis
    try:
        cache.set('health_check', 'ok', 10)
        if cache.get('health_check') == 'ok':
            checks['cache'] = 'ok'
        else:
            checks['cache'] = 'error: cache not working'
    except Exception as e:
        checks['cache'] = f'error: {e}'

    # Redis direto (para Celery)
    try:
        r = redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=2)
        r.ping()
        checks['redis'] = 'ok'
    except Exception as e:
        checks['redis'] = f'error: {e}'

    # Status geral
    all_ok = all(v == 'ok' for v in checks.values())
    status = 200 if all_ok else 503

    return JsonResponse({
        'status': 'healthy' if all_ok else 'unhealthy',
        'checks': checks
    }, status=status)