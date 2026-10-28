"""Changing the password revokes every access token, as it revokes every session."""
from django.conf import settings
from django.db.models.signals import post_init, post_save
from django.dispatch import receiver
from django.utils import timezone


@receiver(post_init, sender=settings.AUTH_USER_MODEL)
def _remember_password(sender, instance, **kwargs):
    instance._assistant_password = instance.password


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def _revoke_tokens_on_password_change(sender, instance, created, **kwargs):
    if created or instance.password == getattr(instance, '_assistant_password', instance.password):
        return
    from .models import PersonalAccessToken
    PersonalAccessToken.objects.filter(user=instance, revoked_at__isnull=True).update(revoked_at=timezone.now())
    instance._assistant_password = instance.password
