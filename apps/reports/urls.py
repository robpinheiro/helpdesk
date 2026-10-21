# apps/reports/urls.py — URLs dos Relatórios
# =========================================

from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('tickets/', views.relatorio_tickets, name='tickets'),
]