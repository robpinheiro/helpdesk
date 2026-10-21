# apps/accounts/views.py — Views de perfil do usuário
# ==================================================

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect
from django.utils.translation import gettext_lazy as _

from .forms import UserProfileForm


@login_required
def perfil(request):
    """Exibe perfil do usuário logado"""
    return render(request, 'accounts/perfil.html', {
        'user': request.user,
    })


@login_required
def editar_perfil(request):
    """Edita perfil do usuário logado (campos não-LDAP)"""
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, _('Perfil atualizado com sucesso!'))
            return redirect('accounts:perfil')
    else:
        form = UserProfileForm(instance=request.user)

    return render(request, 'accounts/editar_perfil.html', {'form': form})