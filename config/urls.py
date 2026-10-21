# config/urls.py — URLs principais
# ================================

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView
from apps.core.views import health_check

urlpatterns = [
    # Health check (para load balancer / nginx)
    path('health/', health_check, name='health_check'),

    # Admin
    path('admin/', admin.site.urls),

    # Apps
    path('', include('apps.tickets.urls')),
    path('accounts/', include('apps.accounts.urls')),
    path('reports/', include('apps.reports.urls')),

    # API (futuro)
    # path('api/', include('apps.api.urls')),
]

# Admin customization
admin.site.site_header = 'Helpdesk - Administração'
admin.site.site_title = 'Helpdesk Admin'
admin.site.index_title = 'Painel de Controle'

# Static/Media em desenvolvimento
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)