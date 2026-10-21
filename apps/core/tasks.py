# apps/core/tasks.py — Tasks Celery (sync LDAP, backup, emails)
# ============================================================

from celery import shared_task
from django.utils import timezone
from django.core.management import call_command
from django.conf import settings
import subprocess
import os
import tempfile
import shutil
from .models import LDAPConfiguration, BackupConfiguration


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def sync_ldap_users(self):
    """Sincroniza usuários e técnicos do LDAP"""
    config = LDAPConfiguration.load()
    if not config or not config.sync_enabled:
        return "LDAP sync desabilitado ou não configurado"

    try:
        call_command('sync_ldap_users')
        config.last_sync = timezone.now()
        config.save(update_fields=['last_sync'])
        return f"Sync concluído em {config.last_sync}"
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=600)
def run_backup_task(self, config_pk):
    """Executa backup completo (DB + Media)"""
    try:
        config = BackupConfiguration.objects.get(pk=config_pk)
    except BackupConfiguration.DoesNotExist:
        return "Configuração de backup não encontrada"

    config.last_status = 'running'
    config.save(update_fields=['last_status'])

    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"helpdesk_backup_{timestamp}"

    # Diretório temporário
    with tempfile.TemporaryDirectory(prefix=f'{backup_name}_') as tmp_dir:
        try:
            # 1. pg_dump (formato custom para restore paralelo)
            db_file = os.path.join(tmp_dir, 'db.dump')
            db_cmd = [
                'pg_dump',
                '-h', os.environ.get('DB_HOST', 'postgres'),
                '-U', os.environ.get('DB_USER', 'helpdesk'),
                '-d', os.environ.get('DB_NAME', 'helpdesk'),
                '-F', 'c',  # custom format
                '-f', db_file,
                '--no-owner',
                '--no-privileges',
            ]
            env = {**os.environ, 'PGPASSWORD': os.environ.get('DB_PASSWORD', '')}
            subprocess.run(db_cmd, check=True, env=env, capture_output=True, text=True, timeout=300)

            # 2. Media files
            media_file = os.path.join(tmp_dir, 'media.tar.gz')
            media_src = '/app/media'
            if os.path.exists(media_src):
                subprocess.run(
                    ['tar', '-czf', media_file, '-C', media_src, '.'],
                    check=True, capture_output=True, timeout=300
                )

            # 3. Static files (opcional, menor)
            static_file = os.path.join(tmp_dir, 'static.tar.gz')
            static_src = '/app/static'
            if os.path.exists(static_src):
                subprocess.run(
                    ['tar', '-czf', static_file, '-C', static_src, '.'],
                    check=True, capture_output=True, timeout=60
                )

            # 4. Move para destino
            dest_path = _store_backup(config, tmp_dir, backup_name)

            # 5. Limpeza de backups antigos (retention)
            _cleanup_old_backups(config)

            config.last_backup = timezone.now()
            config.last_status = f'success: {dest_path}'
            config.save(update_fields=['last_backup', 'last_status'])
            return f"Backup salvo em {dest_path}"

        except subprocess.CalledProcessError as e:
            error_msg = f'Command failed: {e.stderr.decode() if e.stderr else str(e)}'
            config.last_status = f'error: {error_msg[:200]}'
            config.save(update_fields=['last_status'])
            raise self.retry(exc=Exception(error_msg))
        except Exception as e:
            config.last_status = f'error: {str(e)[:200]}'
            config.save(update_fields=['last_status'])
            raise


def _store_backup(config, tmp_dir, backup_name):
    """Armazena backup conforme backend configurado"""
    dest = config.storage_path.rstrip('/')

    if config.storage_backend == 'local':
        final_dest = f"{dest}/{backup_name}"
        os.makedirs(final_dest, exist_ok=True)
        for item in os.listdir(tmp_dir):
            shutil.move(os.path.join(tmp_dir, item), os.path.join(final_dest, item))
        return final_dest

    elif config.storage_backend == 'nfs':
        # Assume NFS já montado no caminho
        final_dest = f"{dest}/{backup_name}"
        os.makedirs(final_dest, exist_ok=True)
        for item in os.listdir(tmp_dir):
            shutil.move(os.path.join(tmp_dir, item), os.path.join(final_dest, item))
        return final_dest

    elif config.storage_backend == 's3':
        # Usa boto3 para upload
        import boto3
        from botocore.config import Config

        s3 = boto3.client(
            's3',
            endpoint_url=config.s3_endpoint or None,
            aws_access_key_id=config.s3_access_key,
            aws_secret_access_key=config.s3_secret_key,
            region_name=config.s3_region or 'us-east-1',
            config=Config(signature_version='s3v4')
        )

        bucket = config.storage_path
        for item in os.listdir(tmp_dir):
            local_file = os.path.join(tmp_dir, item)
            key = f"{backup_name}/{item}"
            s3.upload_file(local_file, bucket, key)
        return f"s3://{bucket}/{backup_name}/"

    return "unknown"


def _cleanup_old_backups(config):
    """Remove backups mais antigos que retention_days"""
    if config.storage_backend in ('local', 'nfs'):
        base_path = config.storage_path
        if not os.path.exists(base_path):
            return

        cutoff = timezone.now().timestamp() - (config.retention_days * 86400)
        for item in os.listdir(base_path):
            item_path = os.path.join(base_path, item)
            if os.path.isdir(item_path):
                # Verifica timestamp no nome (helpdesk_backup_YYYYMMDD_HHMMSS)
                try:
                    ts_str = item.replace('helpdesk_backup_', '')
                    item_time = timezone.datetime.strptime(ts_str, '%Y%m%d_%H%M%S').timestamp()
                    if item_time < cutoff:
                        shutil.rmtree(item_path)
                except ValueError:
                    pass  # Nome não segue padrão, ignora

    elif config.storage_backend == 's3':
        # Cleanup S3 - listar objetos e deletar antigos
        import boto3
        from botocore.config import Config

        s3 = boto3.client(
            's3',
            endpoint_url=config.s3_endpoint or None,
            aws_access_key_id=config.s3_access_key,
            aws_secret_access_key=config.s3_secret_key,
            region_name=config.s3_region or 'us-east-1',
            config=Config(signature_version='s3v4')
        )

        bucket = config.storage_path
        paginator = s3.get_paginator('list_objects_v2')
        cutoff = timezone.now().timestamp() - (config.retention_days * 86400)

        for page in paginator.paginate(Bucket=bucket, Prefix='helpdesk_backup_'):
            for obj in page.get('Contents', []):
                # Extrai timestamp do prefixo
                try:
                    prefix = obj['Key'].split('/')[0]
                    ts_str = prefix.replace('helpdesk_backup_', '')
                    obj_time = timezone.datetime.strptime(ts_str, '%Y%m%d_%H%M%S').timestamp()
                    if obj_time < cutoff:
                        s3.delete_object(Bucket=bucket, Key=obj['Key'])
                except (ValueError, IndexError):
                    pass


@shared_task
def check_and_run_scheduled_backups():
    """Verifica agendamento e dispara backups (roda a cada hora via Celery Beat)"""
    from django.utils import timezone
    now = timezone.now()

    for config in BackupConfiguration.objects.filter(enabled=True):
        should_run = False

        if config.frequency == 'daily':
            should_run = (now.hour == config.time.hour and now.minute == config.time.minute)
        elif config.frequency == 'weekly':
            # Segunda-feira = 0
            should_run = (now.weekday() == 0 and now.hour == config.time.hour and now.minute == config.time.minute)
        elif config.frequency == 'monthly':
            should_run = (now.day == 1 and now.hour == config.time.hour and now.minute == config.time.minute)

        if should_run:
            run_backup_task.delay(config.pk)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_ticket_email(self, subject, message, recipient_list, from_email=None):
    """Envia e-mail assíncrono para notificações de ticket"""
    from django.core.mail import send_mail
    from .models import EmailConfiguration

    email_config = EmailConfiguration.load()
    if not email_config or not email_config.is_active:
        return "E-mail desabilitado"

    try:
        connection = get_connection(
            backend='django.core.mail.backends.smtp.EmailBackend',
            host=email_config.host,
            port=email_config.port,
            username=email_config.username,
            password=email_config.password,
            use_tls=email_config.use_tls,
            use_ssl=email_config.use_ssl,
        )
        send_mail(
            subject,
            message,
            from_email or email_config.from_email,
            recipient_list,
            fail_silently=False,
            connection=connection,
        )
        return f"E-mail enviado para {', '.join(recipient_list)}"
    except Exception as exc:
        raise self.retry(exc=exc)


def get_connection(**kwargs):
    from django.core.mail import get_connection as django_get_connection
    return django_get_connection(**kwargs)