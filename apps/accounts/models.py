# apps/accounts/models.py — Custom User Model + Profile
# ====================================================

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class User(AbstractUser):
    """Usuário customizado - campos adicionais além do AbstractUser"""
    # O AbstractUser já tem: username, first_name, last_name, email, is_staff, is_active, date_joined, etc.
    # Adicionamos apenas campos específicos do helpdesk

    telefone = models.CharField(_("Telefone"), max_length=20, blank=True)
    departamento = models.CharField(_("Departamento"), max_length=100, blank=True)
    cargo = models.CharField(_("Cargo"), max_length=100, blank=True)

    # LDAP sync metadata
    ldap_dn = models.CharField(_("LDAP DN"), max_length=255, blank=True, editable=False)
    last_ldap_sync = models.DateTimeField(_("Último Sync LDAP"), null=True, blank=True, editable=False)

    class Meta:
        verbose_name = _("Usuário")
        verbose_name_plural = _("Usuários")
        ordering = ['first_name', 'last_name', 'username']

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def is_tecnico(self):
        """Verifica se o usuário é técnico (tem perfil Tecnico ativo)"""
        return hasattr(self, 'tecnico_profile') and self.tecnico_profile.ativo

    def get_tickets_solicitados(self):
        return self.tickets_solicitados.all()

    def get_tickets_atendidos(self):
        if self.is_tecnico:
            return self.tecnico_profile.tickets_atendidos.all()
        return self.tickets_atendidos.none()


class Tecnico(models.Model):
    """Perfil de técnico - sincronizado do grupo LDAP"""

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='tecnico_profile',
        verbose_name=_("Usuário")
    )
    ativo = models.BooleanField(_("Ativo"), default=True)
    # Opcional: especialidades, nível, etc.
    especialidades = models.TextField(_("Especialidades"), blank=True,
        help_text="Uma por linha")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Técnico")
        verbose_name_plural = _("Técnicos")
        ordering = ['usuario__first_name', 'usuario__last_name']

    def __str__(self):
        return f"{self.usuario.get_full_name()} ({'Ativo' if self.ativo else 'Inativo'})"

    def get_tickets_abertos(self):
        return self.tickets_atendidos.filter(status__in=['aberto', 'em_andamento'])

    def get_tickets_count_mes(self):
        from django.utils import timezone
        from datetime import timedelta
        inicio_mes = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return self.tickets_atendidos.filter(created_at__gte=inicio_mes).count()