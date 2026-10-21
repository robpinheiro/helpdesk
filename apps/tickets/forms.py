# apps/tickets/forms.py — Forms para Tickets
# ==========================================

from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Ticket, TicketAnexo, TicketComentario
from apps.accounts.models import Tecnico


class TicketForm(forms.ModelForm):
    """Form para criação/edição de ticket"""

    class Meta:
        model = Ticket
        fields = ['solicitante', 'tecnico', 'data_ocorrido', 'problema', 'prioridade', 'status',
                  'observacoes', 'solucao', 'tempo_gasto']
        widgets = {
            'solicitante': forms.Select(attrs={'class': 'form-select select2'}),
            'tecnico': forms.Select(attrs={'class': 'form-select select2'}),
            'data_ocorrido': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'problema': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Descreva o problema...'}),
            'prioridade': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'observacoes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Observações adicionais...'}),
            'solucao': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'O que foi feito para resolver...'}),
            'tempo_gasto': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'HH:MM:SS'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Técnicos ativos para seleção
        self.fields['tecnico'].queryset = Tecnico.objects.filter(ativo=True).select_related('usuario')

        # Se não é superuser, limita solicitante
        if user and not user.is_superuser:
            self.fields['solicitante'].queryset = user.__class__.objects.filter(pk=user.pk)
            self.fields['solicitante'].initial = user
            self.fields['solicitante'].disabled = True


class TicketCreateForm(TicketForm):
    """Form simplificado para criação rápida (modal)"""

    class Meta(TicketForm.Meta):
        fields = ['solicitante', 'data_ocorrido', 'problema', 'prioridade']
        widgets = {
            'solicitante': forms.HiddenInput(),  # Preenchido automaticamente
            'data_ocorrido': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'problema': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Descreva o problema...'}),
            'prioridade': forms.Select(attrs={'class': 'form-select'}),
        }


class TicketUpdateForm(TicketForm):
    """Form para atualização (técnico/admin)"""

    class Meta(TicketForm.Meta):
        fields = ['tecnico', 'status', 'observacoes', 'solucao', 'tempo_gasto']


class TicketAnexoForm(forms.ModelForm):
    """Form para upload de anexos"""

    class Meta:
        model = TicketAnexo
        fields = ['arquivo', 'descricao']
        widgets = {
            'arquivo': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*,application/pdf'}),
            'descricao': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Descrição opcional'}),
        }

    def clean_arquivo(self):
        arquivo = self.cleaned_data.get('arquivo')
        if arquivo:
            # Valida tamanho (max 10MB)
            if arquivo.size > 10 * 1024 * 1024:
                raise forms.ValidationError(_('Arquivo muito grande. Máximo 10MB.'))
            # Valida tipo
            allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'application/pdf']
            if hasattr(arquivo, 'content_type') and arquivo.content_type not in allowed_types:
                raise forms.ValidationError(_('Tipo de arquivo não permitido. Use imagens (JPG, PNG, GIF, WebP) ou PDF.'))
        return arquivo


class TicketComentarioForm(forms.ModelForm):
    """Form para comentários"""

    class Meta:
        model = TicketComentario
        fields = ['texto', 'interno']
        widgets = {
            'texto': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Adicione um comentário...'}),
            'interno': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        # Apenas técnicos veem checkbox "interno"
        if user and not (hasattr(user, 'tecnico_profile') and user.tecnico_profile.ativo):
            self.fields['interno'].widget = forms.HiddenInput()
            self.fields['interno'].initial = False