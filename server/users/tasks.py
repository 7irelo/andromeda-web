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
def send_password_reset_email(user_id, reset_link):
    try:
        from django.contrib.auth import get_user_model
        from django.core.mail import send_mail
        from django.conf import settings
        User = get_user_model()
        user = User.objects.get(id=user_id)
        send_mail(
            subject='Reset your Andromeda password',
            message=f'Hi {user.first_name},\n\nClick the link below to reset your password:\n{reset_link}\n\nIf you did not request this, ignore this email.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
    except Exception as e:
        logger.error(f'send_password_reset_email error: {e}')
