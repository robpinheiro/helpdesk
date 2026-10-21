# apps/tickets/apps.py
from django.apps import AppConfig


class TicketsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.tickets'
    verbose_name = 'Tickets/Chamados'

    def ready(self):
        # Import signals se houver
        pass