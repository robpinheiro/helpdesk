# apps/reports/tasks.py — Tasks para geração/envio de relatórios
# ===========================================================

from celery import shared_task
from django.utils import timezone
from django.core.mail import EmailMessage, get_connection
from django.conf import settings
from django.db.models import Count, Avg
from django.template.loader import render_to_string
import csv
import io

from .models import RelatorioAgendado
from apps.tickets.models import Ticket
from apps.accounts.models import Tecnico
from apps.core.models import EmailConfiguration


def _get_email_connection():
    """Cria conexão SMTP usando config do Admin"""
    email_config = EmailConfiguration.load()
    if not email_config or not email_config.is_active:
        return None
    return get_connection(
        backend='django.core.mail.backends.smtp.EmailBackend',
        host=email_config.host,
        port=email_config.port,
        username=email_config.username,
        password=email_config.password,
        use_tls=email_config.use_tls,
        use_ssl=email_config.use_ssl,
    )


def _generate_report_data(relatorio):
    """Gera queryset filtrado conforme config do relatório"""
    tickets = Ticket.objects.select_related('solicitante', 'tecnico__usuario').all()

    if relatorio.status_filter:
        tickets = tickets.filter(status__in=relatorio.status_filter)
    if relatorio.prioridade_filter:
        tickets = tickets.filter(prioridade__in=relatorio.prioridade_filter)
    if relatorio.tecnico_filter:
        tickets = tickets.filter(tecnico_id__in=relatorio.tecnico_filter)
    if relatorio.date_range_days:
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(days=relatorio.date_range_days)
        tickets = tickets.filter(created_at__gte=cutoff)

    return tickets


def _generate_csv(tickets):
    """Gera CSV em memória"""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Solicitante', 'Técnico', 'Status', 'Prioridade', 'Data Ocorrido', 'Criado em', 'Resolvido em', 'Problema', 'Solução', 'Tempo Gasto'])

    for t in tickets.iterator():
        writer.writerow([
            t.pk,
            t.solicitante.get_full_name() or t.solicitante.username,
            t.tecnico.usuario.get_full_name() if t.tecnico else '',
            t.get_status_display(),
            t.get_prioridade_display(),
            t.data_ocorrido.strftime('%d/%m/%Y %H:%M'),
            t.created_at.strftime('%d/%m/%Y %H:%M'),
            t.resolvido_em.strftime('%d/%m/%Y %H:%M') if t.resolvido_em else '',
            t.problema[:200],
            t.solucao[:200],
            _format_tempo(t.tempo_gasto.total_seconds()) if t.tempo_gasto else '',
        ])
    return output.getvalue().encode('utf-8')


def _generate_excel(tickets):
    """Gera Excel em memória"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, PatternFill
    except ImportError:
        return None

    wb = Workbook()
    ws = wb.active
    ws.title = 'Tickets'

    headers = ['ID', 'Solicitante', 'Técnico', 'Status', 'Prioridade', 'Data Ocorrido', 'Criado em', 'Resolvido em', 'Problema', 'Solução', 'Tempo Gasto']
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='3B82F6', end_color='3B82F6', fill_type='solid')

    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')

    for row, t in enumerate(tickets.iterator(), 2):
        ws.cell(row=row, column=1, value=t.pk)
        ws.cell(row=row, column=2, value=t.solicitante.get_full_name() or t.solicitante.username)
        ws.cell(row=row, column=3, value=t.tecnico.usuario.get_full_name() if t.tecnico else '')
        ws.cell(row=row, column=4, value=t.get_status_display())
        ws.cell(row=row, column=5, value=t.get_prioridade_display())
        ws.cell(row=row, column=6, value=t.data_ocorrido.strftime('%d/%m/%Y %H:%M'))
        ws.cell(row=row, column=7, value=t.created_at.strftime('%d/%m/%Y %H:%M'))
        ws.cell(row=row, column=8, value=t.resolvido_em.strftime('%d/%m/%Y %H:%M') if t.resolvido_em else '')
        ws.cell(row=row, column=9, value=t.problema[:500])
        ws.cell(row=row, column=10, value=t.solucao[:500])
        ws.cell(row=row, column=11, value=_format_tempo(t.tempo_gasto.total_seconds()) if t.tempo_gasto else '')

    for col in ws.columns:
        max_length = max(len(str(cell.value or '')) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_length + 2, 50)

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


def _generate_pdf(tickets, relatorio):
    """Gera PDF simples via reportlab"""
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.units import cm
    except ImportError:
        return None

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(A4), leftMargin=1*cm, rightMargin=1*cm, topMargin=1*cm, bottomMargin=1*cm)
    styles = getSampleStyleSheet()
    elements = []

    # Título
    title = Paragraph(f"Relatório de Tickets - {relatorio.nome}", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 0.5*cm))

    # Data
    data = [['ID', 'Solicitante', 'Técnico', 'Status', 'Prioridade', 'Data Ocorrido', 'Problema', 'Solução']]
    for t in tickets[:500]:  # Limita para não estourar memória
        data.append([
            str(t.pk),
            t.solicitante.get_full_name() or t.solicitante.username,
            t.tecnico.usuario.get_full_name() if t.tecnico else '',
            t.get_status_display(),
            t.get_prioridade_display(),
            t.data_ocorrido.strftime('%d/%m/%Y'),
            t.problema[:100],
            t.solucao[:100],
        ])

    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3B82F6')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F3F4F6')]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(table)

    doc.build(elements)
    return output.getvalue()


def _format_tempo(seconds):
    if seconds is None:
        return ''
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def gerar_e_enviar_relatorio(self, relatorio_pk):
    """Task principal: gera relatório e envia por e-mail"""
    try:
        relatorio = RelatorioAgendado.objects.get(pk=relatorio_pk)
    except RelatorioAgendado.DoesNotExist:
        return "Relatório não encontrado"

    relatorio.last_status = 'generating'
    relatorio.save(update_fields=['last_status'])

    try:
        # Gera dados
        tickets = _generate_report_data(relatorio)
        total = tickets.count()

        if total == 0:
            relatorio.last_status = 'empty: nenhum ticket encontrado'
            relatorio.save(update_fields=['last_status'])
            return "Nenhum ticket encontrado"

        # Gera arquivo
        filename_base = f"relatorio_{relatorio.nome.replace(' ', '_')}_{timezone.now().strftime('%Y%m%d_%H%M%S')}"
        attachment = None
        mime_type = ''

        if relatorio.format == 'csv':
            content = _generate_csv(tickets)
            filename = f"{filename_base}.csv"
            mime_type = 'text/csv'
            attachment = (filename, content, mime_type)
        elif relatorio.format == 'excel':
            content = _generate_excel(tickets)
            if content:
                filename = f"{filename_base}.xlsx"
                mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                attachment = (filename, content, mime_type)
        elif relatorio.format == 'pdf':
            content = _generate_pdf(tickets, relatorio)
            if content:
                filename = f"{filename_base}.pdf"
                mime_type = 'application/pdf'
                attachment = (filename, content, mime_type)

        if not attachment:
            relatorio.last_status = 'error: falha ao gerar arquivo'
            relatorio.save(update_fields=['last_status'])
            return "Falha ao gerar arquivo"

        # Envia e-mail
        connection = _get_email_connection()
        if not connection:
            relatorio.last_status = 'error: e-mail não configurado'
            relatorio.save(update_fields=['last_status'])
            return "E-mail não configurado"

        subject = f"[Helpdesk] Relatório: {relatorio.nome}"
        body = f"""
Olá,

Segue em anexo o relatório "{relatorio.nome}" gerado em {timezone.now().strftime('%d/%m/%Y %H:%M')}.

Total de tickets: {total}
Período: últimos {relatorio.date_range_days} dias
Filtros aplicados: {', '.join(filter(None, [
    f"Status: {relatorio.status_filter}" if relatorio.status_filter else '',
    f"Prioridade: {relatorio.prioridade_filter}" if relatorio.prioridade_filter else '',
    f"Técnicos: {relatorio.tecnico_filter}" if relatorio.tecnico_filter else '',
])) or 'Nenhum'}

--
Sistema Helpdesk
        """.strip()

        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=f"{EmailConfiguration.load().from_name} <{EmailConfiguration.load().from_email}>",
            to=relatorio.get_recipients_list(),
            cc=relatorio.get_cc_list(),
            connection=connection,
        )
        email.attach(*attachment)
        email.send()

        relatorio.last_sent = timezone.now()
        relatorio.last_status = f'sent: {total} tickets'
        relatorio.save(update_fields=['last_sent', 'last_status'])
        return f"Relatório enviado para {len(relatorio.get_recipients_list())} destinatário(s)"

    except Exception as e:
        relatorio.last_status = f'error: {str(e)[:200]}'
        relatorio.save(update_fields=['last_status'])
        raise self.retry(exc=e)


@shared_task
def check_and_send_scheduled_reports():
    """Verifica agendamento e dispara relatórios (roda a cada hora via Celery Beat)"""
    from django.utils import timezone
    now = timezone.now()

    for rel in RelatorioAgendado.objects.filter(enabled=True):
        should_run = False

        if rel.frequency == 'daily':
            should_run = (now.hour == rel.time.hour and now.minute == rel.time.minute)
        elif rel.frequency == 'weekly':
            should_run = (now.weekday() == rel.day_of_week and now.hour == rel.time.hour and now.minute == rel.time.minute)
        elif rel.frequency == 'monthly':
            should_run = (now.day == 1 and now.hour == rel.time.hour and now.minute == rel.time.minute)

        if should_run:
            gerar_e_enviar_relatorio.delay(rel.pk)