# apps/tickets/views.py — Views HTMX para Tickets
# ==============================================

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods, require_POST
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Ticket, TicketAnexo, TicketComentario
from .forms import TicketForm, TicketCreateForm, TicketUpdateForm, TicketAnexoForm, TicketComentarioForm
from apps.accounts.models import Tecnico


@login_required
def ticket_list(request):
    """Lista de tickets com filtros (HTMX)"""
    tickets = Ticket.objects.select_related('solicitante', 'tecnico__usuario').all()

    # Filtros
    status = request.GET.get('status')
    prioridade = request.GET.get('prioridade')
    tecnico_id = request.GET.get('tecnico')
    search = request.GET.get('search')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    # Permissões: não-superuser vê apenas seus
    if not request.user.is_superuser:
        if hasattr(request.user, 'tecnico_profile') and request.user.tecnico_profile.ativo:
            tickets = tickets.filter(Q(solicitante=request.user) | Q(tecnico=request.user.tecnico_profile))
        else:
            tickets = tickets.filter(solicitante=request.user)

    if status:
        tickets = tickets.filter(status=status)
    if prioridade:
        tickets = tickets.filter(prioridade=prioridade)
    if tecnico_id:
        tickets = tickets.filter(tecnico_id=tecnico_id)
    if search:
        tickets = tickets.filter(
            Q(problema__icontains=search) |
            Q(solucao__icontains=search) |
            Q(solicitante__first_name__icontains=search) |
            Q(solicitante__last_name__icontains=search) |
            Q(solicitante__username__icontains=search)
        )
    if date_from:
        tickets = tickets.filter(created_at__date__gte=date_from)
    if date_to:
        tickets = tickets.filter(created_at__date__lte=date_to)

    # Paginação
    paginator = Paginator(tickets, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    # Para selects de filtro
    tecnicos = Tecnico.objects.filter(ativo=True).select_related('usuario')

    context = {
        'page_obj': page_obj,
        'tecnicos': tecnicos,
        'status_choices': Ticket.STATUS_CHOICES,
        'prioridade_choices': Ticket.PRIORIDADE_CHOICES,
        'current_filters': request.GET,
    }

    # HTMX partial
    if request.headers.get('HX-Request'):
        return render(request, 'tickets/partials/ticket_list_rows.html', context)

    return render(request, 'tickets/list.html', context)


@login_required
def ticket_detail(request, pk):
    """Detalhe do ticket (com timeline, anexos, comentários)"""
    ticket = get_object_or_404(
        Ticket.objects.select_related('solicitante', 'tecnico__usuario').prefetch_related('anexos', 'comentarios__autor'),
        pk=pk
    )

    # Permissão
    if not ticket.pode_editar(request.user) and not request.user.is_superuser:
        messages.error(request, _('Você não tem permissão para ver este ticket.'))
        return redirect('tickets:list')

    # Forms
    update_form = TicketUpdateForm(instance=ticket, user=request.user)
    anexo_form = TicketAnexoForm()
    comentario_form = TicketComentarioForm(user=request.user)

    context = {
        'ticket': ticket,
        'update_form': update_form,
        'anexo_form': anexo_form,
        'comentario_form': comentario_form,
        'anexos': ticket.anexos.all(),
        'comentarios': ticket.comentarios.all(),
    }

    return render(request, 'tickets/detail.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def ticket_create(request):
    """Criação de ticket (modal HTMX)"""
    if request.method == 'POST':
        form = TicketCreateForm(request.POST, user=request.user)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.solicitante = request.user
            ticket.save()
            messages.success(request, _('Ticket criado com sucesso!'))
            # Retorna o ticket criado para HTMX inserir na lista
            response = HttpResponse(status=204)
            response['HX-Trigger'] = 'ticketCreated'
            return response
    else:
        form = TicketCreateForm(user=request.user)
        form.fields['solicitante'].initial = request.user

    return render(request, 'tickets/partials/create_modal.html', {'form': form})


@login_required
@require_POST
def ticket_update(request, pk):
    """Atualização de ticket (HTMX)"""
    ticket = get_object_or_404(Ticket, pk=pk)

    if not ticket.pode_editar(request.user) and not request.user.is_superuser:
        return HttpResponse(_('Sem permissão'), status=403)

    form = TicketUpdateForm(request.POST, instance=ticket, user=request.user)
    if form.is_valid():
        form.save()
        messages.success(request, _('Ticket atualizado!'))
        return render(request, 'tickets/partials/ticket_card.html', {'ticket': ticket})

    return render(request, 'tickets/partials/update_form.html', {'form': form, 'ticket': ticket})


@login_required
@require_POST
def ticket_add_anexo(request, pk):
    """Upload de anexo (HTMX)"""
    ticket = get_object_or_404(Ticket, pk=pk)

    if not ticket.pode_editar(request.user) and not request.user.is_superuser:
        return HttpResponse(_('Sem permissão'), status=403)

    form = TicketAnexoForm(request.POST, request.FILES)
    if form.is_valid():
        anexo = form.save(commit=False)
        anexo.ticket = ticket
        anexo.enviado_por = request.user
        anexo.save()
        return render(request, 'tickets/partials/anexo_item.html', {'anexo': anexo})

    return HttpResponse(_('Erro no upload'), status=400)


@login_required
@require_POST
def ticket_add_comentario(request, pk):
    """Adiciona comentário (HTMX)"""
    ticket = get_object_or_404(Ticket, pk=pk)

    if not ticket.pode_editar(request.user) and not request.user.is_superuser:
        return HttpResponse(_('Sem permissão'), status=403)

    form = TicketComentarioForm(request.POST, user=request.user)
    if form.is_valid():
        comentario = form.save(commit=False)
        comentario.ticket = ticket
        comentario.autor = request.user
        comentario.save()
        return render(request, 'tickets/partials/comentario_item.html', {'comentario': comentario})

    return HttpResponse(_('Erro ao adicionar comentário'), status=400)


@login_required
@require_POST
def ticket_delete_anexo(request, pk):
    """Remove anexo"""
    anexo = get_object_or_404(TicketAnexo, pk=pk)
    ticket = anexo.ticket

    if not ticket.pode_editar(request.user) and not request.user.is_superuser:
        return HttpResponse(_('Sem permissão'), status=403)

    anexo.delete()
    return HttpResponse(status=204)


@login_required
def ticket_search_solicitante(request):
    """Busca usuários para autocomplete (HTMX)"""
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})

    from django.contrib.auth import get_user_model
    User = get_user_model()

    users = User.objects.filter(
        Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(username__icontains=q) | Q(email__icontains=q)
    )[:10]

    results = [{'id': u.pk, 'text': f"{u.get_full_name()} ({u.username})", 'username': u.username} for u in users]
    return JsonResponse({'results': results})


@login_required
def dashboard(request):
    """Dashboard com KPIs"""
    from django.db.models import Count, Avg
    from datetime import timedelta

    # Base queryset com permissões
    tickets = Ticket.objects.all()
    if not request.user.is_superuser:
        if hasattr(request.user, 'tecnico_profile') and request.user.tecnico_profile.ativo:
            tickets = tickets.filter(Q(solicitante=request.user) | Q(tecnico=request.user.tecnico_profile))
        else:
            tickets = tickets.filter(solicitante=request.user)

    # KPIs
    hoje = timezone.now().date()
    inicio_mes = hoje.replace(day=1)
    inicio_semana = hoje - timedelta(days=hoje.weekday())

    kpis = {
        'total_abertos': tickets.filter(status='aberto').count(),
        'total_em_andamento': tickets.filter(status='em_andamento').count(),
        'total_resolvidos_mes': tickets.filter(status__in=['resolvido', 'fechado'], resolvido_em__date__gte=inicio_mes).count(),
        'total_criados_mes': tickets.filter(created_at__date__gte=inicio_mes).count(),
        'meus_abertos': tickets.filter(solicitante=request.user, status__in=['aberto', 'em_andamento']).count(),
    }

    if hasattr(request.user, 'tecnico_profile') and request.user.tecnico_profile.ativo:
        kpis['meus_atribuidos'] = tickets.filter(tecnico=request.user.tecnico_profile, status__in=['aberto', 'em_andamento']).count()

    # Tickets recentes
    recentes = tickets.select_related('solicitante', 'tecnico__usuario')[:10]

    # Por status (para gráfico)
    por_status = tickets.values('status').annotate(count=Count('id'))
    status_data = {item['status']: item['count'] for item in por_status}

    # Por prioridade
    por_prioridade = tickets.values('prioridade').annotate(count=Count('id'))
    prioridade_data = {item['prioridade']: item['count'] for item in por_prioridade}

    context = {
        'kpis': kpis,
        'recentes': recentes,
        'status_data': status_data,
        'prioridade_data': prioridade_data,
    }
    return render(request, 'tickets/dashboard.html', context)