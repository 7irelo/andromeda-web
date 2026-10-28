"""
Account security: device sessions, TOTP two-factor sign-in and email verification.

- Sessions: every sign-in creates a `UserSession` whose id rides in the
  refresh token as `sid`. Refresh is refused once the session is revoked, so
  "sign out this device" works without waiting for the token to expire.
- TOTP: RFC 6238 via pyotp. The secret is encrypted with a key derived from
  SECRET_KEY (HKDF, purpose-bound), each time step is accepted once, and
  recovery codes are single-use and stored as password hashes.
- Login with 2FA is two steps: the password step returns a short-lived signed
  challenge instead of a session; the code step exchanges it for a session.
- Email verification links are signed, time-limited and bound to the email
  address they were sent to, so changing the address invalidates old links.
"""
import base64
import ipaddress
import secrets
import uuid

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core import signing
from django.core.cache import cache
from django.utils import timezone

from .models import MFADevice, UserSession

ISSUER = 'Andromeda'
MFA_CHALLENGE_SALT = 'andromeda.mfa-challenge'
MFA_CHALLENGE_SECONDS = 300
MFA_MAX_ATTEMPTS = 5
EMAIL_VERIFY_SALT = 'andromeda.email-verify'
EMAIL_VERIFY_SECONDS = 3 * 24 * 3600
RECOVERY_CODES = 10


# ── Sessions ─────────────────────────────────────────────────────────────────

def _client_ip(request):
    # Behind nginx the real address is in X-Real-IP; REMOTE_ADDR otherwise.
    return (request.META.get('HTTP_X_REAL_IP') or request.META.get('REMOTE_ADDR') or '').strip()


def _ip_prefix(raw):
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        return ''
    net = ipaddress.ip_network(f'{ip}/{24 if ip.version == 4 else 48}', strict=False)
    return str(net)


def start_session(user, request):
    return UserSession.objects.create(
        id=uuid.uuid4(), user=user,
        user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:200],
        ip_prefix=_ip_prefix(_client_ip(request)),
    )


def touch_session(sid):
    """True if the session is live; records activity at most once a minute."""
    try:
        session_id = uuid.UUID(str(sid))
    except (TypeError, ValueError):
        return False
    s = UserSession.objects.filter(pk=session_id, revoked_at__isnull=True).first()
    if s is None:
        return False
    now = timezone.now()
    if (now - s.last_seen_at).total_seconds() > 60:
        UserSession.objects.filter(pk=s.pk).update(last_seen_at=now)
    return True


def revoke_sessions(user, exclude=None):
    qs = UserSession.objects.filter(user=user, revoked_at__isnull=True)
    if exclude:
        qs = qs.exclude(pk=exclude)
    qs.update(revoked_at=timezone.now())


# ── TOTP secret encryption ───────────────────────────────────────────────────

def _fernet():
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=b'andromeda-mfa', info=b'totp-secret-v1') \
        .derive(settings.SECRET_KEY.encode())
    return Fernet(base64.urlsafe_b64encode(key))


def _encrypt(secret):
    return _fernet().encrypt(secret.encode()).decode()


def _decrypt(token):
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None


# ── TOTP ─────────────────────────────────────────────────────────────────────

def begin_setup(user):
    """(Re)start setup with a fresh secret. Enabling needs a valid code."""
    secret = pyotp.random_base32()
    device, _ = MFADevice.objects.update_or_create(
        user=user, defaults={'secret_encrypted': _encrypt(secret), 'enabled': False, 'last_step': 0,
                             'recovery_codes': [], 'enabled_at': None},
    )
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=ISSUER)
    return secret, uri


def qr_data_uri(uri):
    """A PNG data URI of the provisioning QR code (PNG, so the client needs no sanitizer bypass)."""
    import io

    import segno
    buf = io.BytesIO()
    segno.make(uri, error='m').save(buf, kind='png', scale=5, border=2)
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


def _accept_totp(device, code):
    secret = _decrypt(device.secret_encrypted)
    if not secret or not code or not code.isdigit():
        return False
    totp = pyotp.TOTP(secret)
    now = timezone.now().timestamp()
    for drift in (0, -1, 1):  # allow one step of clock skew either way
        step = int(now // totp.interval) + drift
        if step <= device.last_step:
            continue
        if secrets.compare_digest(totp.at(step * totp.interval), code):
            MFADevice.objects.filter(pk=device.pk).update(last_step=step)
            device.last_step = step
            return True
    return False


def _accept_recovery(device, code):
    code = (code or '').replace('-', '').replace(' ', '').lower()
    if len(code) != 10:
        return False
    remaining = list(device.recovery_codes)
    for i, hashed in enumerate(remaining):
        if check_password(code, hashed):
            del remaining[i]
            MFADevice.objects.filter(pk=device.pk).update(recovery_codes=remaining)
            device.recovery_codes = remaining
            return True
    return False


def verify_code(device, code, allow_recovery=True):
    code = (code or '').strip()
    if _accept_totp(device, code):
        return True
    return allow_recovery and _accept_recovery(device, code)


def enable(device, code):
    if device.enabled or not _accept_totp(device, (code or '').strip()):
        return None
    codes = [secrets.token_hex(5) for _ in range(RECOVERY_CODES)]
    device.recovery_codes = [make_password(c) for c in codes]
    device.enabled = True
    device.enabled_at = timezone.now()
    device.save(update_fields=['recovery_codes', 'enabled', 'enabled_at'])
    return [f'{c[:5]}-{c[5:]}' for c in codes]


def mfa_enabled(user):
    return MFADevice.objects.filter(user=user, enabled=True).exists()


# ── Login challenge ──────────────────────────────────────────────────────────

def issue_challenge(user):
    nonce = secrets.token_urlsafe(16)
    return signing.dumps({'uid': user.pk, 'n': nonce}, salt=MFA_CHALLENGE_SALT)


def redeem_challenge(token):
    """The user id for a valid, unexpired challenge with attempts left, else None."""
    try:
        data = signing.loads(token, salt=MFA_CHALLENGE_SALT, max_age=MFA_CHALLENGE_SECONDS)
    except signing.BadSignature:
        return None
    key = f'mfa-attempts:{data["n"]}'
    attempts = cache.get(key, 0)
    if attempts >= MFA_MAX_ATTEMPTS:
        return None
    cache.set(key, attempts + 1, MFA_CHALLENGE_SECONDS)
    return data['uid'], key


def spend_challenge(key):
    # A used challenge can't be replayed.
    cache.set(key, MFA_MAX_ATTEMPTS, MFA_CHALLENGE_SECONDS)


# ── Email verification ───────────────────────────────────────────────────────

def email_token(user):
    return signing.dumps({'uid': user.pk, 'e': user.email.lower()}, salt=EMAIL_VERIFY_SALT)


def verify_email_token(token):
    from django.contrib.auth import get_user_model
    try:
        data = signing.loads(token, salt=EMAIL_VERIFY_SALT, max_age=EMAIL_VERIFY_SECONDS)
    except signing.BadSignature:
        return None
    user = get_user_model().objects.filter(pk=data.get('uid'), is_active=True).first()
    if user is None or user.email.lower() != data.get('e'):
        return None
    return user
