# apps/reports/models.py — Modelos para Relatórios
# ===============================================

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class RelatorioAgendado(models.Model):
    """Relatórios agendados para envio por e-mail"""

    FREQUENCY_CHOICES = [
        ('daily', 'Diário'),
        ('weekly', 'Semanal'),
        ('monthly', 'Mensal'),
    ]

    FORMAT_CHOICES = [
        ('pdf', 'PDF'),
        ('excel', 'Excel'),
        ('csv', 'CSV'),
    ]

    nome = models.CharField(_("Nome"), max_length=100)
    descricao = models.TextField(_("Descrição"), blank=True)

    # Filtros do relatório
    status_filter = models.JSONField(_("Filtro de Status"), default=list, blank=True)
    prioridade_filter = models.JSONField(_("Filtro de Prioridade"), default=list, blank=True)
    tecnico_filter = models.JSONField(_("Filtro de Técnico"), default=list, blank=True)
    date_range_days = models.PositiveIntegerField(_("Período (dias)"), default=30)

    # Agendamento
    frequency = models.CharField(_("Frequência"), max_length=10, choices=FREQUENCY_CHOICES, default='weekly')
    day_of_week = models.PositiveIntegerField(_("Dia da Semana (0=Seg)"), default=0, choices=[(i, d) for i, d in enumerate(['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'])])
    time = models.TimeField(_("Horário"), default='08:00')

    # Formato e destinatários
    format = models.CharField(_("Formato"), max_length=10, choices=FORMAT_CHOICES, default='pdf')
    recipients = models.TextField(_("Destinatários (e-mails)"), help_text="Um por linha")
    cc_recipients = models.TextField(_("CC (e-mails)"), blank=True)

    # Status
    enabled = models.BooleanField(_("Ativo"), default=True)
    last_sent = models.DateTimeField(_("Último Envio"), null=True, blank=True)
    last_status = models.CharField(_("Status"), max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='relatorios_criados')

    class Meta:
        verbose_name = _("Relatório Agendado")
        verbose_name_plural = _("Relatórios Agendados")
        ordering = ['nome']

    def __str__(self):
        return self.nome

    def get_recipients_list(self):
        return [e.strip() for e in self.recipients.split('\n') if e.strip()]

    def get_cc_list(self):
        return [e.strip() for e in self.cc_recipients.split('\n') if e.strip()]