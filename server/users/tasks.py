"""
Celery tasks for users – runs on the 'emails' queue.
"""
from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task(name='users.tasks.send_welcome_email', queue='emails')
def send_welcome_email(user_id):
    try:
        from django.contrib.auth import get_user_model
        from django.core.mail import send_mail
        from django.conf import settings
        User = get_user_model()
        user = User.objects.get(id=user_id)
        send_mail(
            subject='Welcome to Andromeda!',
            message=f'Hi {user.first_name},\n\nWelcome to Andromeda! Start connecting with people around you.\n\nThe Andromeda Team',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
        logger.info(f'Welcome email sent to {user.email}')
    except Exception as e:
        logger.error(f'send_welcome_email error: {e}')


@shared_task(name='users.tasks.send_password_reset_email', queue='emails')
def send_password_reset_email(user_id):
    # The token is minted here rather than passed in, so it never sits in the
    # broker, the result backend or Flower.
    try:
        from django.contrib.auth import get_user_model
        from django.contrib.auth.tokens import default_token_generator
        from django.core.mail import send_mail
        from django.conf import settings
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        User = get_user_model()
        user = User.objects.get(id=user_id, is_active=True)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        reset_link = f'{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}'
        send_mail(
            subject='Reset your Andromeda password',
            message=f'Hi {user.first_name},\n\nClick the link below to reset your password:\n{reset_link}\n\nIf you did not request this, ignore this email.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
    except Exception as e:
        logger.error(f'send_password_reset_email error: {e}')


@shared_task(name='users.tasks.send_verification_email', queue='emails')
def send_verification_email(user_id):
    # Minted here, like the reset token, so the link never sits in the broker.
    try:
        from django.contrib.auth import get_user_model
        from django.core.mail import send_mail
        from django.conf import settings
        from .security import email_token
        user = get_user_model().objects.get(id=user_id, is_active=True)
        if user.email_verified:
            return
        link = f'{settings.FRONTEND_URL}/verify-email?token={email_token(user)}'
        send_mail(
            subject='Confirm your email for Andromeda',
            message=f'Hi {user.first_name or user.username},\n\nConfirm your email address:\n{link}\n\n'
                    'The link expires in 3 days. If you did not create an account, ignore this email.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
    except Exception as e:
        logger.error(f'send_verification_email error: {e}')


@shared_task(name='users.tasks.run_data_export', queue='default')
def run_data_export(export_id):
    from .models import DataExport
    from .privacy import run_export
    export = DataExport.objects.select_related('user').filter(pk=export_id, status=DataExport.STATUS_PENDING).first()
    if export is None:
        return
    run_export(export)
    if export.status == DataExport.STATUS_READY:
        from django.conf import settings
        from django.core.mail import send_mail
        send_mail(subject='Your Andromeda data export is ready', from_email=settings.DEFAULT_FROM_EMAIL,
                  recipient_list=[export.user.email], fail_silently=True,
                  message=f'Download it from Settings while signed in: {settings.FRONTEND_URL}/settings\n\n'
                          'The file is available for 7 days.')


@shared_task(name='users.tasks.send_deletion_scheduled_email', queue='emails')
def send_deletion_scheduled_email(user_id):
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.core.mail import send_mail
    user = get_user_model().objects.filter(pk=user_id, deletion_scheduled_at__isnull=False).first()
    if user is None:
        return
    send_mail(subject='Your Andromeda account will be deleted', from_email=settings.DEFAULT_FROM_EMAIL,
              recipient_list=[user.email], fail_silently=True,
              message=f'Your account and everything in it will be permanently deleted on '
                      f'{user.deletion_scheduled_at:%d %B %Y}.\n\nChanged your mind? Sign in before then to '
                      f'cancel: {settings.FRONTEND_URL}/login\n\nIf you did not ask for this, sign in now and '
                      'change your password.')


@shared_task(name='users.tasks.erase_due_accounts', queue='default')
def erase_due_accounts():
    from django.contrib.auth import get_user_model
    from django.utils import timezone
    from .privacy import erase
    due = get_user_model().objects.filter(deletion_scheduled_at__lte=timezone.now())
    count = 0
    for user in due.iterator():
        erase(user)
        count += 1
    return count


@shared_task(name='users.tasks.expire_data_exports', queue='default')
def expire_data_exports():
    from django.utils import timezone
    from .models import DataExport
    old = DataExport.objects.filter(expires_at__lt=timezone.now())
    count = old.count()
    for e in old:
        e.delete()  # core.media_cleanup removes the file
    return count
