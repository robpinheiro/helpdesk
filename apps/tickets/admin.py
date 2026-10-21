# apps/tickets/admin.py — Admin para Tickets, Anexos, Comentários
# ===============================================================

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from .models import Ticket, TicketAnexo, TicketComentario


class TicketAnexoInline(admin.TabularInline):
    model = TicketAnexo
    extra = 0
    readonly_fields = ['criado_em', 'enviado_por', 'preview']
    fields = ['arquivo', 'descricao', 'preview', 'criado_em', 'enviado_por']
    can_delete = False

    def preview(self, obj):
        if obj.pk and obj.is_image:
            return format_html('<a href="{}" target="_blank"><img src="{}" style="max-height:60px;"></a>', obj.arquivo.url, obj.arquivo.url)
        return '-'
    preview.short_description = _('Preview')


class TicketComentarioInline(admin.TabularInline):
    model = TicketComentario
    extra = 0
    readonly_fields = ['autor', 'criado_em', 'interno']
    fields = ['texto', 'interno', 'autor', 'criado_em']
    can_delete = False
    ordering = ['-criado_em']


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ['id', 'solicitante_nome', 'tecnico_nome', 'status_badge', 'prioridade_badge', 'data_ocorrido', 'created_at', 'tempo_gasto_display']
    list_filter = ['status', 'prioridade', 'tecnico', 'created_at', 'resolvido_em']
    search_fields = ['id', 'solicitante__username', 'solicitante__first_name', 'solicitante__last_name', 'solicitante__email', 'problema', 'solucao']
    readonly_fields = ['created_at', 'updated_at', 'resolvido_em', 'fechado_em', 'history_log']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    list_per_page = 25
    inlines = [TicketComentarioInline, TicketAnexoInline]

    fieldsets = [
        (_('Informações Básicas'), {
            'fields': ['solicitante', 'tecnico', 'data_ocorrido', 'prioridade', 'status']
        }),
        (_('Descrição do Problema'), {
            'fields': ['problema'],
            'classes': ['wide']
        }),
        (_('Resolução'), {
            'fields': ['observacoes', 'solucao', 'tempo_gasto'],
            'classes': ['wide']
        }),
        (_('Datas'), {
            'fields': ['created_at', 'updated_at', 'resolvido_em', 'fechado_em'],
            'classes': ['collapse']
        }),
    ]

    def solicitante_nome(self, obj):
        return obj.solicitante.get_full_name() or obj.solicitante.username
    solicitante_nome.short_description = _('Solicitante')
    solicitante_nome.admin_order_field = 'solicitante__first_name'

    def tecnico_nome(self, obj):
        if obj.tecnico:
            return obj.tecnico.usuario.get_full_name() or obj.tecnico.usuario.username
        return '-'
    tecnico_nome.short_description = _('Técnico')

    def status_badge(self, obj):
        colors = {
            'aberto': '#3b82f6',
            'em_andamento': '#f59e0b',
            'resolvido': '#10b981',
            'fechado': '#6b7280',
            'cancelado': '#ef4444',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:500;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = _('Status')
    status_badge.admin_order_field = 'status'

    def prioridade_badge(self, obj):
        colors = {
            'baixa': '#10b981',
            'media': '#3b82f6',
            'alta': '#f59e0b',
            'critica': '#ef4444',
        }
        color = colors.get(obj.prioridade, '#6b7280')
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:500;">{}</span>',
            color, obj.get_prioridade_display()
        )
    prioridade_badge.short_description = _('Prioridade')
    prioridade_badge.admin_order_field = 'prioridade'

    def tempo_gasto_display(self, obj):
        if obj.tempo_gasto:
            total_seconds = int(obj.tempo_gasto.total_seconds())
            h = total_seconds // 3600
            m = (total_seconds % 3600) // 60
            s = total_seconds % 60
            return f"{h:02d}:{m:02d}:{s:02d}"
        return '-'
    tempo_gasto_display.short_description = _('Tempo Gasto')

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related('solicitante', 'tecnico__usuario')
        # Não-superuser vê apenas seus tickets (solicitados ou atribuídos)
        if not request.user.is_superuser:
            if hasattr(request.user, 'tecnico_profile') and request.user.tecnico_profile.ativo:
                qs = qs.filter(models.Q(solicitante=request.user) | models.Q(tecnico=request.user.tecnico_profile))
            else:
                qs = qs.filter(solicitante=request.user)
        return qs

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return True
        return obj.pode_editar(request.user)


@admin.register(TicketAnexo)
class TicketAnexoAdmin(admin.ModelAdmin):
    list_display = ['id', 'ticket_link', 'descricao', 'enviado_por', 'criado_em', 'file_size_mb']
    list_filter = ['criado_em']
    search_fields = ['ticket__id', 'descricao', 'enviado_por__username']
    readonly_fields = ['criado_em', 'ticket', 'enviado_por']

    def ticket_link(self, obj):
        from django.urls import reverse
        url = reverse('admin:tickets_ticket_change', args=[obj.ticket_id])
        return format_html('<a href="{}">#{}</a>', url, obj.ticket_id)
    ticket_link.short_description = _('Ticket')


@admin.register(TicketComentario)
class TicketComentarioAdmin(admin.ModelAdmin):
    list_display = ['id', 'ticket_link', 'autor', 'interno_badge', 'criado_em']
    list_filter = ['interno', 'criado_em']
    search_fields = ['ticket__id', 'texto', 'autor__username']
    readonly_fields = ['criado_em']

    def ticket_link(self, obj):
        from django.urls import reverse
        url = reverse('admin:tickets_ticket_change', args=[obj.ticket_id])
        return format_html('<a href="{}">#{}</a>', url, obj.ticket_id)
    ticket_link.short_description = _('Ticket')

    def interno_badge(self, obj):
        if obj.interno:
            return format_html('<span style="background:#f59e0b;color:white;padding:2px 6px;border-radius:8px;font-size:10px;">Interno</span>')
        return format_html('<span style="background:#3b82f6;color:white;padding:2px 6px;border-radius:8px;font-size:10px;">Público</span>')
    interno_badge.short_description = _('Visibilidade')