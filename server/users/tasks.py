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
