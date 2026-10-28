"""
Generate a VAPID key pair for Web Push.

    python manage.py vapid_keys

Prints the two lines to put in .env. The private key is shown once and never
stored by this command.
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand


def _b64url(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


class Command(BaseCommand):
    help = 'Generate a VAPID key pair for Web Push.'

    def handle(self, *args, **options):
        key = ec.generate_private_key(ec.SECP256R1())
        private = key.private_numbers().private_value.to_bytes(32, 'big')
        public = key.public_key().public_bytes(serialization.Encoding.X962,
                                               serialization.PublicFormat.UncompressedPoint)
        self.stdout.write(f'VAPID_PUBLIC_KEY={_b64url(public)}')
        self.stdout.write(f'VAPID_PRIVATE_KEY={_b64url(private)}')
