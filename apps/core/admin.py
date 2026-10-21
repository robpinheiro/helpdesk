# apps/core/admin.py — Admin personalizado para configurações
# ==========================================================

from django.contrib import admin
from django import forms
from django.urls import path, reverse
from django.utils.html import format_html
from django.contrib import messages
from django.core.mail import send_mail, get_connection
from django.utils.translation import gettext_lazy as _

from .models import LDAPConfiguration, EmailConfiguration, BackupConfiguration
from .views import ldap_test_connection, ldap_browse_ous, ldap_browse_groups


class SingletonAdmin(admin.ModelAdmin):
    """Admin base para modelos singleton"""

    def has_add_permission(self, request):
        return not self.model.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Redireciona para a edição do único objeto
        obj = self.model.load()
        return self.changeform_view(request, str(obj.pk))


class LDAPConfigForm(forms.ModelForm):
    class Meta:
        model = LDAPConfiguration
        fields = '__all__'
        widgets = {
            'bind_password': forms.PasswordInput(render_value=True),
            'users_base_dn': forms.TextInput(attrs={
                'readonly': True,
                'data-ldap-browser': 'ou',
                'style': 'cursor:pointer; background:#f5f5f5;'
            }),
            'tecnicos_group_dn': forms.TextInput(attrs={
                'readonly': True,
                'data-ldap-browser': 'group',
                'style': 'cursor:pointer; background:#f5f5f5;'
            }),
        }


@admin.register(LDAPConfiguration)
class LDAPConfigurationAdmin(SingletonAdmin):
    form = LDAPConfigForm
    change_form_template = 'admin/core/ldapconfig/change_form.html'
    fieldsets = [
        (_('Conexão'), {
            'fields': ['server_uri', 'bind_dn', 'bind_password'],
            'description': 'Dados de conexão com o servidor LDAP (Samba 4 / AD)'
        }),
        (_('Usuários'), {
            'fields': ['users_base_dn', 'login_attribute', 'user_filter'],
            'description': 'Configure onde buscar usuários e qual atributo usar como login'
        }),
        (_('Técnicos'), {
            'fields': ['tecnicos_group_dn'],
            'description': 'Grupo do AD cujos membros serão técnicos no helpdesk'
        }),
        (_('Sincronização'), {
            'fields': ['sync_interval_hours', 'sync_enabled', 'last_sync'],
        }),
    ]
    readonly_fields = ['last_sync']

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('ldap-test/', self.admin_site.admin_view(ldap_test_connection), name='ldap_test'),
            path('ldap-browse-ous/', self.admin_site.admin_view(ldap_browse_ous), name='ldap_browse_ous'),
            path('ldap-browse-groups/', self.admin_site.admin_view(ldap_browse_groups), name='ldap_browse_groups'),
        ]
        return custom + urls

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['test_url'] = reverse('admin:ldap_test')
        extra_context['browse_ous_url'] = reverse('admin:ldap_browse_ous')
        extra_context['browse_groups_url'] = reverse('admin:ldap_browse_groups')
        return super().change_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
        # Invalida cache do backend LDAP
        from django.core.cache import cache
        cache.delete('ldap_config')
        messages.success(request, "Configuração LDAP salva. O cache foi limpo.")


class EmailConfigForm(forms.ModelForm):
    class Meta:
        model = EmailConfiguration
        fields = '__all__'
        widgets = {
            'password': forms.PasswordInput(render_value=True),
        }


@admin.register(EmailConfiguration)
class EmailConfigurationAdmin(SingletonAdmin):
    form = EmailConfigForm
    fieldsets = [
        (_('Servidor'), {'fields': ['host', 'port', 'use_tls', 'use_ssl']}),
        (_('Credenciais'), {'fields': ['username', 'password', 'from_email', 'from_name']}),
        (_('Teste'), {'fields': ['test_recipient', 'is_active']}),
    ]

    def save_model(self, request, obj, form, change):
        # Testa envio se preencheu test_recipient
        if obj.test_recipient and obj.is_active:
            try:
                connection = get_connection(
                    backend='django.core.mail.backends.smtp.EmailBackend',
                    host=obj.host,
                    port=obj.port,
                    username=obj.username,
                    password=obj.password,
                    use_tls=obj.use_tls,
                    use_ssl=obj.use_ssl,
                )
                send_mail(
                    'Teste Helpdesk - Configuração de E-mail',
                    'Esta é uma mensagem de teste da configuração de e-mail do Helpdesk.',
                    obj.from_email,
                    [obj.test_recipient],
                    fail_silently=False,
                    connection=connection,
                )
                messages.success(request, f"E-mail de teste enviado com sucesso para {obj.test_recipient}!")
            except Exception as e:
                messages.error(request, f"Falha no teste de e-mail: {e}")
        super().save_model(request, obj, form, change)


class BackupConfigForm(forms.ModelForm):
    class Meta:
        model = BackupConfiguration
        fields = '__all__'


@admin.register(BackupConfiguration)
class BackupConfigurationAdmin(SingletonAdmin):
    form = BackupConfigForm
    list_display = ['frequency', 'time', 'retention_days', 'storage_backend', 'enabled', 'last_backup', 'last_status']
    readonly_fields = ['last_backup', 'last_status']
    actions = ['run_backup_now']

    fieldsets = [
        (_('Agendamento'), {'fields': ['frequency', 'time', 'retention_days', 'enabled']}),
        (_('Destino'), {'fields': ['storage_backend', 'storage_path']}),
        (_('S3 (opcional)'), {
            'fields': ['s3_endpoint', 's3_access_key', 's3_secret_key', 's3_region'],
            'classes': ['collapse'],
            'description': 'Preencha apenas se o destino for S3/MinIO'
        }),
        (_('Status'), {'fields': ['last_backup', 'last_status']}),
    ]

    @admin.action(description='Executar backup agora')
    def run_backup_now(self, request, queryset):
        from .tasks import run_backup_task
        for config in queryset:
            run_backup_task.delay(config.pk)
        self.message_user(request, "Backup agendado (assíncrono). Verifique o status em instantes.")