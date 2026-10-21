# apps/accounts/forms.py — Forms de usuário/perfil
# ===============================================

from django import forms
from django.contrib.auth.forms import UserChangeForm
from .models import User


class UserProfileForm(forms.ModelForm):
    """Form para edição de perfil (campos não sincronizados do LDAP)"""

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'telefone', 'departamento', 'cargo']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'telefone': forms.TextInput(attrs={'class': 'form-control'}),
            'departamento': forms.TextInput(attrs={'class': 'form-control'}),
            'cargo': forms.TextInput(attrs={'class': 'form-control'}),
        }