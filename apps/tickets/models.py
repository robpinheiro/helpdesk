# apps/tickets/models.py — Modelos de Tickets, Anexos, Histórico
# ===========================================================

from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords


class Ticket(models.Model):
    """Ticket/Chamado de Helpdesk"""

    STATUS_CHOICES = [
        ('aberto', _('Aberto')),
        ('em_andamento', _('Em Andamento')),
        ('resolvido', _('Resolvido')),
        ('fechado', _('Fechado')),
        ('cancelado', _('Cancelado')),
    ]

    PRIORIDADE_CHOICES = [
        ('baixa', _('Baixa')),
        ('media', _('Média')),
        ('alta', _('Alta')),
        ('critica', _('Crítica')),
    ]

    # Campos obrigatórios
    solicitante = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='tickets_solicitados',
        verbose_name=_("Solicitante")
    )
    tecnico = models.ForeignKey(
        'accounts.Tecnico',
        on_delete=models.PROTECT,
        related_name='tickets_atendidos',
        null=True, blank=True,
        verbose_name=_("Técnico Responsável")
    )
    data_ocorrido = models.DateTimeField(_("Data do Ocorrido"), default=timezone.now)
    problema = models.TextField(_("Problema"), help_text=_("Descreva o que está acontecendo"))
    prioridade = models.CharField(_("Prioridade"), max_length=10, choices=PRIORIDADE_CHOICES, default='media')
    status = models.CharField(_("Status"), max_length=15, choices=STATUS_CHOICES, default='aberto')

    # Campos de resolução
    observacoes = models.TextField(_("Observações"), blank=True, help_text=_("Observações adicionais"))
    solucao = models.TextField(_("Solução"), blank=True, help_text=_("O que foi feito para resolver"))
    tempo_gasto = models.DurationField(_("Tempo Gasto"), null=True, blank=True,
        help_text=_("Formato: HH:MM:SS ou use o cronômetro"))

    # Metadados
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Criado em"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Atualizado em"))
    resolvido_em = models.DateTimeField(_("Resolvido em"), null=True, blank=True)
    fechado_em = models.DateTimeField(_("Fechado em"), null=True, blank=True)

    # Histórico (django-simple-history)
    history = HistoricalRecords(
        related_name='history_log',
        excluded_fields=['updated_at'],
        change_reason_field=models.TextField(_("Motivo da Alteração"), blank=True)
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = _("Ticket")
        verbose_name_plural = _("Tickets")
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['tecnico', 'status']),
            models.Index(fields=['solicitante', 'created_at']),
            models.Index(fields=['prioridade', 'status']),
        ]
        permissions = [
            ('view_all_tickets', _('Pode ver todos os tickets')),
            ('assign_ticket', _('Pode atribuir tickets')),
        ]

    def __str__(self):
        return f"#{self.pk} - {self.solicitante.get_full_name() or self.solicitante.username} - {self.get_status_display()}"

    def save(self, *args, **kwargs):
        # Auto-preenche datas de status
        if self.pk:
            old = Ticket.objects.get(pk=self.pk)
            if old.status != self.status:
                now = timezone.now()
                if self.status == 'resolvido' and not self.resolvido_em:
                    self.resolvido_em = now
                elif self.status == 'fechado' and not self.fechado_em:
                    self.fechado_em = now
        super().save(*args, **kwargs)

    @property
    def tempo_decorrido(self):
        """Tempo desde criação até agora (ou resolução)"""
        fim = self.resolvido_em or self.fechado_em or timezone.now()
        return fim - self.created_at

    @property
    def is_aberto(self):
        return self.status == 'aberto'

    @property
    def is_em_andamento(self):
        return self.status == 'em_andamento'

    @property
    def is_finalizado(self):
        return self.status in ['resolvido', 'fechado', 'cancelado']

    def pode_editar(self, user):
        """Verifica se usuário pode editar este ticket"""
        if user.is_superuser:
            return True
        if user == self.solicitante and self.status == 'aberto':
            return True
        if hasattr(user, 'tecnico_profile') and user.tecnico_profile.ativo:
            if self.tecnico == user.tecnico_profile or not self.tecnico:
                return True
        return False

    def pode_atribuir(self, user):
        return user.is_superuser or (hasattr(user, 'tecnico_profile') and user.tecnico_profile.ativo and user.has_perm('tickets.assign_ticket'))


class TicketAnexo(models.Model):
    """Anexos/Fotos de comprovação de resolução"""

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='anexos', verbose_name=_("Ticket"))
    arquivo = models.FileField(_("Arquivo"), upload_to='tickets/%Y/%m/%d/')
    descricao = models.CharField(_("Descrição"), max_length=255, blank=True)
    enviado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_("Enviado por"))
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name=_("Criado em"))

    # Histórico
    history = HistoricalRecords(excluded_fields=['criado_em'])

    class Meta:
        ordering = ['-criado_em']
        verbose_name = _("Anexo")
        verbose_name_plural = _("Anexos")

    def __str__(self):
        return f"Anexo #{self.pk} - Ticket #{self.ticket_id}"

    @property
    def is_image(self):
        ext = self.arquivo.name.lower().split('.')[-1]
        return ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp']

    @property
    def file_size_mb(self):
        try:
            return round(self.arquivo.size / (1024 * 1024), 2)
        except:
            return 0


class TicketComentario(models.Model):
    """Comentários/Atualizações no ticket (timeline)"""

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='comentarios', verbose_name=_("Ticket"))
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_("Autor"))
    texto = models.TextField(_("Comentário"))
    interno = models.BooleanField(_("Interno (apenas técnicos)"), default=False)
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name=_("Criado em"))

    class Meta:
        ordering = ['criado_em']
        verbose_name = _("Comentário")
        verbose_name_plural = _("Comentários")

    def __str__(self):
        return f"Comentário #{self.pk} - Ticket #{self.ticket_id}"

    def save(self, *args, **kwargs):
        # Se técnico comenta e ticket estava aberto, muda para em_andamento
        if self.ticket.status == 'aberto' and hasattr(self.autor, 'tecnico_profile'):
            self.ticket.status = 'em_andamento'
            self.ticket.save(update_fields=['status', 'updated_at'])
        super().save(*args, **kwargs)