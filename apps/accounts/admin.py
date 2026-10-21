# apps/accounts/admin.py — Admin para User e Tecnico
# =================================================

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from .models import User, Tecnico


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'get_full_name', 'email', 'departamento', 'is_staff', 'is_active', 'is_tecnico', 'last_ldap_sync']
    list_filter = ['is_staff', 'is_superuser', 'is_active', 'departamento']
    search_fields = ['username', 'first_name', 'last_name', 'email', 'departamento']
    ordering = ['first_name', 'last_name', 'username']
    readonly_fields = ['last_login', 'date_joined', 'ldap_dn', 'last_ldap_sync']

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Informações Pessoais'), {'fields': ('first_name', 'last_name', 'email', 'telefone', 'departamento', 'cargo')}),
        (_('Permissões'), {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        (_('Datas Importantes'), {'fields': ('last_login', 'date_joined')}),
        (_('LDAP'), {'fields': ('ldap_dn', 'last_ldap_sync'), 'classes': ('collapse',)}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'first_name', 'last_name', 'email', 'password1', 'password2'),
        }),
    )

    def is_tecnico(self, obj):
        return obj.is_tecnico
    is_tecnico.boolean = True
    is_tecnico.short_description = _('É Técnico')


@admin.register(Tecnico)
class TecnicoAdmin(admin.ModelAdmin):
    list_display = ['usuario', 'ativo', 'especialidades_preview', 'created_at', 'tickets_abertos_count']
    list_filter = ['ativo', 'created_at']
    search_fields = ['usuario__username', 'usuario__first_name', 'usuario__last_name', 'usuario__email', 'especialidades']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        (None, {'fields': ('usuario', 'ativo', 'especialidades')}),
        (_('Datas'), {'fields': ('created_at', 'updated_at')}),
    )

    def especialidades_preview(self, obj):
        if obj.especialidades:
            lines = obj.especialidades.strip().split('\n')
            return ', '.join(lines[:3]) + ('...' if len(lines) > 3 else '')
        return '-'
    especialidades_preview.short_description = _('Especialidades')

    def tickets_abertos_count(self, obj):
        return obj.get_tickets_abertos().count()
    tickets_abertos_count.short_description = _('Tickets Abertos')