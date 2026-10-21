# apps/accounts/management/commands/sync_ldap_users.py — Sincroniza usuários/grupos do LDAP
# =================================================================================

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.accounts.backends import get_ldap_connection, search_ldap_users, get_ldap_group_members
from apps.accounts.models import Tecnico
from apps.core.models import LDAPConfiguration

User = get_user_model()


class Command(BaseCommand):
    help = 'Sincroniza usuários e técnicos do LDAP (Samba 4 / AD)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--full',
            action='store_true',
            help='Sync completo (cria usuários que não existem)',
        )
        parser.add_argument(
            '--tecnicos-only',
            action='store_true',
            help='Apenas sincroniza grupo de técnicos',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simula sem salvar alterações',
        )

    def handle(self, *args, **options):
        config = LDAPConfiguration.load()
        if not config or not config.server_uri:
            self.stderr.write(self.style.ERROR('LDAP não configurado. Configure em Admin > Core > LDAP Configuration.'))
            return

        self.stdout.write(f"Conectando em {config.server_uri}...")

        conn = get_ldap_connection()
        if not conn:
            self.stderr.write(self.style.ERROR('Falha na conexão LDAP'))
            return

        self.stdout.write(self.style.SUCCESS('Conectado com sucesso'))

        # 1. Sync grupo de técnicos
        if config.tecnicos_group_dn:
            self.sync_tecnicos_group(config, conn, options['dry_run'])

        # 2. Sync usuários (opcional, full sync)
        if options['full'] and not options['tecnicos_only']:
            self.sync_users(config, conn, options['dry_run'])

        # Atualiza timestamp
        if not options['dry_run']:
            config.last_sync = timezone.now()
            config.save(update_fields=['last_sync'])
            self.stdout.write(self.style.SUCCESS(f'Sync concluído em {config.last_sync}'))
        else:
            self.stdout.write(self.style.WARNING('Dry-run: nenhuma alteração salva'))

    def sync_tecnicos_group(self, config, conn, dry_run=False):
        """Sincroniza membros do grupo de técnicos"""
        self.stdout.write(f"Buscando membros do grupo: {config.tecnicos_group_dn}")

        member_dns = get_ldap_group_members(config.tecnicos_group_dn)
        self.stdout.write(f"Encontrados {len(member_dns)} membros no grupo")

        synced = 0
        for member_dn in member_dns:
            # Extrai sAMAccountName do DN (ex: CN=João Silva,OU=Users,DC=empresa,DC=local)
            # Tenta buscar o usuário pelo DN
            try:
                result = conn.search_s(member_dn, 0, '(objectClass=*)', ['sAMAccountName', 'cn', 'mail', 'givenName', 'sn'])
                if not result:
                    continue
                _, attrs = result[0]
                username = attrs.get('sAMAccountName', [b''])[0].decode() if attrs.get('sAMAccountName') else ''
                if not username:
                    continue

                # Busca ou cria usuário
                user, created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        'first_name': attrs.get('givenName', [b''])[0].decode() if attrs.get('givenName') else '',
                        'last_name': attrs.get('sn', [b''])[0].decode() if attrs.get('sn') else '',
                        'email': attrs.get('mail', [b''])[0].decode() if attrs.get('mail') else '',
                        'ldap_dn': member_dn,
                        'last_ldap_sync': timezone.now(),
                    }
                )

                if not created:
                    # Atualiza campos do LDAP
                    user.first_name = attrs.get('givenName', [b''])[0].decode() if attrs.get('givenName') else user.first_name
                    user.last_name = attrs.get('sn', [b''])[0].decode() if attrs.get('sn') else user.last_name
                    user.email = attrs.get('mail', [b''])[0].decode() if attrs.get('mail') else user.email
                    user.ldap_dn = member_dn
                    user.last_ldap_sync = timezone.now()
                    if not dry_run:
                        user.save()

                # Cria/atualiza perfil de técnico
                tecnico, t_created = Tecnico.objects.get_or_create(
                    usuario=user,
                    defaults={'ativo': True}
                )
                if not tecnico.ativo:
                    tecnico.ativo = True
                    if not dry_run:
                        tecnico.save(update_fields=['ativo'])

                action = "Criado" if (created or t_created) else "Atualizado"
                self.stdout.write(f"  {action}: {user.get_full_name()} ({username}) - Técnico: {'Sim' if tecnico.ativo else 'Não'}")
                synced += 1

            except Exception as e:
                self.stderr.write(f"  Erro ao processar {member_dn}: {e}")

        # Desativa técnicos que saíram do grupo
        tecnicos_ativos = Tecnico.objects.filter(ativo=True).select_related('usuario')
        for tecnico in tecnicos_ativos:
            if tecnico.usuario.ldap_dn not in member_dns:
                if not dry_run:
                    tecnico.ativo = False
                    tecnico.save(update_fields=['ativo'])
                self.stdout.write(f"  Desativado: {tecnico.usuario.get_full_name()} (saiu do grupo)")

        self.stdout.write(self.style.SUCCESS(f'Técnicos sincronizados: {synced}'))

    def sync_users(self, config, conn, dry_run=False):
        """Sync completo de usuários da OU configurada"""
        self.stdout.write(f"Buscando usuários em: {config.users_base_dn}")

        filter_str = f'({config.login_attribute}=*)'
        if config.user_filter:
            filter_str = f'(&{filter_str}{config.user_filter})'

        users_data = search_ldap_users(
            base_dn=config.users_base_dn,
            filter_str=filter_str,
            attributes=['cn', 'sn', 'givenName', 'mail', config.login_attribute, 'memberOf'],
            size_limit=0
        )

        self.stdout.write(f"Encontrados {len(users_data)} usuários")

        synced = 0
        for dn, attrs in users_data:
            username = attrs.get(config.login_attribute, [b''])[0].decode() if attrs.get(config.login_attribute) else ''
            if not username:
                continue

            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': attrs.get('givenName', [b''])[0].decode() if attrs.get('givenName') else '',
                    'last_name': attrs.get('sn', [b''])[0].decode() if attrs.get('sn') else '',
                    'email': attrs.get('mail', [b''])[0].decode() if attrs.get('mail') else '',
                    'ldap_dn': dn,
                    'last_ldap_sync': timezone.now(),
                }
            )

            if not created:
                user.first_name = attrs.get('givenName', [b''])[0].decode() if attrs.get('givenName') else user.first_name
                user.last_name = attrs.get('sn', [b''])[0].decode() if attrs.get('sn') else user.last_name
                user.email = attrs.get('mail', [b''])[0].decode() if attrs.get('mail') else user.email
                user.ldap_dn = dn
                user.last_ldap_sync = timezone.now()
                if not dry_run:
                    user.save()

            if created:
                self.stdout.write(f"  Criado: {user.get_full_name()} ({username})")
            synced += 1

        self.stdout.write(self.style.SUCCESS(f'Usuários sincronizados: {synced}'))