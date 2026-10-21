# apps/core/models.py — Modelos de configuração do sistema
# =======================================================

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone


class SingletonModel(models.Model):
    """Modelo base para configurações singleton (apenas 1 instância)"""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # Impede deleção

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj


class LDAPConfiguration(SingletonModel):
    """Configuração única de conexão LDAP (Samba 4 / AD)"""

    # Conexão
    server_uri = models.CharField(_("URI do Servidor"), max_length=255,
        help_text="Ex: ldap://samba4.interno:389 ou ldaps://samba4.interno:636")
    bind_dn = models.CharField(_("DN de Bind (Service Account)"), max_length=255,
        help_text="Ex: cn=helpdesk,ou=services,dc=empresa,dc=local")
    bind_password = models.CharField(_("Senha do Bind"), max_length=255)

    # OU/Base DN dos usuários (selecionável via tree browser)
    users_base_dn = models.CharField(_("Base DN dos Usuários"), max_length=255,
        help_text="OU onde estão os usuários. Ex: ou=users,dc=empresa,dc=local")

    # Atributo de login
    LOGIN_ATTR_CHOICES = [
        ('sAMAccountName', 'sAMAccountName (padrão AD, ex: jsilva)'),
        ('userPrincipalName', 'userPrincipalName (UPN, ex: jsilva@empresa.local)'),
        ('mail', 'mail (e-mail do usuário)'),
    ]
    login_attribute = models.CharField(_("Atributo de Login"), max_length=32,
        choices=LOGIN_ATTR_CHOICES, default='sAMAccountName')

    # Filtro adicional opcional
    user_filter = models.CharField(_("Filtro Extra (LDAP)"), max_length=255, blank=True,
        help_text="Ex: (memberOf=cn=funcionarios,ou=groups,dc=empresa,dc=local)")

    # Grupo de técnicos (selecionável via tree browser)
    tecnicos_group_dn = models.CharField(_("DN do Grupo de Técnicos"), max_length=255, blank=True,
        help_text="Grupo cujos membros viram 'Técnicos' no helpdesk")

    # Sync
    sync_interval_hours = models.PositiveIntegerField(_("Intervalo de Sync (horas)"), default=24,
        validators=[MinValueValidator(1), MaxValueValidator(168)])
    last_sync = models.DateTimeField(_("Último Sync"), null=True, blank=True)
    sync_enabled = models.BooleanField(_("Sync Automático Ativo"), default=True)

    # Metadados
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name=_("Atualizado por"))

    class Meta:
        verbose_name = _("Configuração LDAP")
        verbose_name_plural = _("Configuração LDAP")

    def __str__(self):
        return f"LDAP: {self.server_uri}"

    def get_connection_params(self):
        """Retorna dict com parâmetros para conexão LDAP"""
        return {
            'server_uri': self.server_uri,
            'bind_dn': self.bind_dn,
            'bind_password': self.bind_password,
            'users_base_dn': self.users_base_dn,
            'login_attribute': self.login_attribute,
            'user_filter': self.user_filter,
            'tecnicos_group_dn': self.tecnicos_group_dn,
        }


class EmailConfiguration(SingletonModel):
    """Configuração SMTP para notificações"""

    host = models.CharField(_("Servidor SMTP"), max_length=255)
    port = models.PositiveIntegerField(_("Porta"), default=587)
    use_tls = models.BooleanField(_("Usar TLS"), default=True)
    use_ssl = models.BooleanField(_("Usar SSL"), default=False)
    username = models.CharField(_("Usuário"), max_length=255)
    password = models.CharField(_("Senha"), max_length=255)
    from_email = models.EmailField(_("E-mail Remetente"))
    from_name = models.CharField(_("Nome Remetente"), max_length=100, default="Helpdesk")

    # Teste
    test_recipient = models.EmailField(_("E-mail para Teste"), blank=True)

    is_active = models.BooleanField(_("Ativo"), default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Configuração de E-mail")
        verbose_name_plural = _("Configuração de E-mail")

    def __str__(self):
        return f"SMTP: {self.host}:{self.port}"

    def get_email_backend_config(self):
        """Retorna configuração para django.core.mail"""
        return {
            'EMAIL_BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
            'EMAIL_HOST': self.host,
            'EMAIL_PORT': self.port,
            'EMAIL_HOST_USER': self.username,
            'EMAIL_HOST_PASSWORD': self.password,
            'EMAIL_USE_TLS': self.use_tls,
            'EMAIL_USE_SSL': self.use_ssl,
            'DEFAULT_FROM_EMAIL': f"{self.from_name} <{self.from_email}>",
        }


class BackupConfiguration(SingletonModel):
    """Configuração de backup automático"""

    FREQUENCY_CHOICES = [
        ('daily', 'Diário'),
        ('weekly', 'Semanal'),
        ('monthly', 'Mensal'),
    ]

    STORAGE_CHOICES = [
        ('local', 'Local (volume Docker)'),
        ('nfs', 'NFS/Compartilhamento de Rede'),
        ('s3', 'S3/MinIO Compatível'),
    ]

    frequency = models.CharField(_("Frequência"), max_length=10, choices=FREQUENCY_CHOICES, default='daily')
    time = models.TimeField(_("Horário"), default='02:00')
    retention_days = models.PositiveIntegerField(_("Retenção (dias)"), default=30)

    storage_backend = models.CharField(_("Destino"), max_length=10, choices=STORAGE_CHOICES, default='local')
    storage_path = models.CharField(_("Caminho/Bucket"), max_length=500,
        help_text="Local: /backups | NFS: /mnt/backups | S3: bucket-name")

    # S3 específico (opcional)
    s3_endpoint = models.CharField(_("Endpoint S3"), max_length=255, blank=True)
    s3_access_key = models.CharField(_("Access Key"), max_length=100, blank=True)
    s3_secret_key = models.CharField(_("Secret Key"), max_length=100, blank=True)
    s3_region = models.CharField(_("Região"), max_length=50, blank=True)

    enabled = models.BooleanField(_("Backup Ativo"), default=True)
    last_backup = models.DateTimeField(_("Último Backup"), null=True, blank=True)
    last_status = models.CharField(_("Status"), max_length=200, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Configuração de Backup")
        verbose_name_plural = _("Configuração de Backup")

    def __str__(self):
        return f"Backup: {self.get_frequency_display()} às {self.time}"