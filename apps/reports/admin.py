# apps/reports/admin.py — Admin para Relatórios
# ============================================

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import RelatorioAgendado


@admin.register(RelatorioAgendado)
class RelatorioAgendadoAdmin(admin.ModelAdmin):
    list_display = ['nome', 'frequency', 'day_of_week_display', 'time', 'format', 'enabled', 'last_sent', 'last_status']
    list_filter = ['frequency', 'format', 'enabled']
    search_fields = ['nome', 'descricao']
    readonly_fields = ['last_sent', 'last_status', 'created_at', 'updated_at']
    actions = ['enviar_agora']

    fieldsets = [
        (_('Geral'), {'fields': ['nome', 'descricao', 'enabled']}),
        (_('Filtros'), {
            'fields': ['status_filter', 'prioridade_filter', 'tecnico_filter', 'date_range_days'],
            'classes': ['collapse'],
        }),
        (_('Agendamento'), {'fields': ['frequency', 'day_of_week', 'time']}),
        (_('Entrega'), {'fields': ['format', 'recipients', 'cc_recipients']}),
        (_('Status'), {'fields': ['last_sent', 'last_status', 'created_at', 'updated_at']}),
    ]

    def day_of_week_display(self, obj):
        dias = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
        return dias[obj.day_of_week] if 0 <= obj.day_of_week <= 6 else '-'
    day_of_week_display.short_description = _('Dia da Semana')

    @admin.action(description='Enviar relatório agora')
    def enviar_agora(self, request, queryset):
        from .tasks import gerar_e_enviar_relatorio
        for rel in queryset:
            gerar_e_enviar_relatorio.delay(rel.pk)
        self.message_user(request, "Relatórios agendados para envio.")