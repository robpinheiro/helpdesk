# apps/tickets/urls.py — URLs dos Tickets
# ======================================

from django.urls import path
from . import views

app_name = 'tickets'

urlpatterns = [
    # Dashboard (home)
    path('', views.dashboard, name='dashboard'),

    # Lista
    path('tickets/', views.ticket_list, name='list'),

    # Criação
    path('tickets/novo/', views.ticket_create, name='create'),

    # Detalhe
    path('tickets/<int:pk>/', views.ticket_detail, name='detail'),

    # Atualização (HTMX)
    path('tickets/<int:pk>/editar/', views.ticket_update, name='update'),

    # Anexos
    path('tickets/<int:pk>/anexos/', views.ticket_add_anexo, name='add_anexo'),
    path('anexos/<int:pk>/excluir/', views.ticket_delete_anexo, name='delete_anexo'),

    # Comentários
    path('tickets/<int:pk>/comentarios/', views.ticket_add_comentario, name='add_comentario'),

    # Busca autocomplete
    path('busca/solicitante/', views.ticket_search_solicitante, name='search_solicitante'),
]