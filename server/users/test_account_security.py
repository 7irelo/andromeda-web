"""Device sessions, two-factor sign-in and email verification."""
import pyotp
import pytest
from django.conf import settings
from django.core import mail, signing
from django.test import override_settings
from rest_framework.test import APIClient

from core.test_security import PASSWORD, make_user
from . import security
from .models import MFADevice, UserSession


def login(client, username='alice', password=PASSWORD):
    return client.post('/api/auth/login/', {'username': username, 'password': password}, format='json')


@pytest.fixture
def alice(db):
    return make_user('alice')


def _enable_mfa(user):
    secret, _ = security.begin_setup(user)
    codes = security.enable(user.mfa, pyotp.TOTP(secret).now())
    user.mfa.refresh_from_db()
    return secret, codes


def _next_code(secret, device):
    """A valid code for a later time step than the last accepted one."""
    totp = pyotp.TOTP(secret)
    return totp.at((device.last_step + 1) * totp.interval)


# ── Sessions ─────────────────────────────────────────────────────────────────

class TestSessions:
    def test_login_creates_a_session_carried_in_the_refresh_token(self, alice):
        c = APIClient(HTTP_USER_AGENT='Firefox/140', REMOTE_ADDR='203.0.113.77')
        assert login(c).status_code == 200
        s = UserSession.objects.get(user=alice)
        assert s.user_agent == 'Firefox/140' and s.ip_prefix == '203.0.113.0/24'  # never the full address
        c.force_authenticate(alice)
        rows = c.get('/api/auth/sessions/').json()
        assert len(rows) == 1 and rows[0]['current'] is True

    def test_revoked_session_can_no_longer_refresh(self, alice):
        laptop, phone = APIClient(), APIClient()
        login(laptop)
        login(phone)
        assert UserSession.objects.filter(user=alice).count() == 2
        from rest_framework_simplejwt.tokens import RefreshToken
        phone_sid = RefreshToken(phone.cookies[settings.REFRESH_COOKIE_NAME].value)['sid']
        settings_page = APIClient()
        settings_page.force_authenticate(alice)
        assert settings_page.delete(f'/api/auth/sessions/{phone_sid}/').status_code == 204
        assert phone.post('/api/auth/token/refresh/').status_code == 401
        assert laptop.post('/api/auth/token/refresh/').status_code == 200

    def test_cannot_revoke_someone_elses_session(self, alice):
        bob = make_user('bob')
        login(APIClient(), 'bob')
        c = APIClient()
        c.force_authenticate(alice)
        sid = UserSession.objects.get(user=bob).pk
        assert c.delete(f'/api/auth/sessions/{sid}/').status_code == 404
        assert UserSession.objects.get(pk=sid).revoked_at is None

    def test_logout_and_logout_all_end_sessions(self, alice):
        a, b = APIClient(), APIClient()
        login(a)
        login(b)
        a.post('/api/auth/logout/')
        assert UserSession.objects.filter(user=alice, revoked_at__isnull=True).count() == 1
        b.force_authenticate(alice)
        b.post('/api/auth/logout-all/')
        assert not UserSession.objects.filter(user=alice, revoked_at__isnull=True).exists()


# ── Two-factor sign-in ───────────────────────────────────────────────────────

class TestMFA:
    def test_setup_requires_password_and_enabling_requires_a_valid_code(self, alice):
        c = APIClient()
        c.force_authenticate(alice)
        assert c.post('/api/auth/mfa/setup/', {'password': 'wrong'}, format='json').status_code == 400
        r = c.post('/api/auth/mfa/setup/', {'password': PASSWORD}, format='json')
        assert r.status_code == 200 and r.json()['qr_png'].startswith('data:image/png;base64,')
        secret = r.json()['secret']
        assert c.post('/api/auth/mfa/enable/', {'code': '000000'}, format='json').status_code == 400
        r = c.post('/api/auth/mfa/enable/', {'code': pyotp.TOTP(secret).now()}, format='json')
        assert r.status_code == 200 and len(r.json()['recovery_codes']) == 10

    def test_secret_is_encrypted_at_rest_and_codes_hashed(self, alice):
        secret, codes = _enable_mfa(alice)
        device = MFADevice.objects.get(user=alice)
        assert secret not in device.secret_encrypted
        assert not any(c.replace('-', '') in str(device.recovery_codes) for c in codes)

    def test_password_alone_no_longer_signs_in(self, alice):
        secret, _ = _enable_mfa(alice)
        c = APIClient()
        r = login(c)
        assert r.json().get('mfa_required') is True and 'access' not in r.json()
        assert settings.REFRESH_COOKIE_NAME not in r.cookies
        token = r.json()['mfa_token']
        assert c.post('/api/auth/login/mfa/', {'mfa_token': token, 'code': '123456'}, format='json').status_code == 400
        alice.mfa.refresh_from_db()
        r = c.post('/api/auth/login/mfa/', {'mfa_token': token, 'code': _next_code(secret, alice.mfa)}, format='json')
        assert r.status_code == 200 and 'access' in r.json()

    def test_codes_and_challenges_cannot_be_replayed(self, alice):
        secret, _ = _enable_mfa(alice)
        c = APIClient()
        token = login(c).json()['mfa_token']
        code = _next_code(secret, alice.mfa)
        assert c.post('/api/auth/login/mfa/', {'mfa_token': token, 'code': code}, format='json').status_code == 200
        # Same challenge again, and the same code on a fresh challenge, both fail.
        assert c.post('/api/auth/login/mfa/', {'mfa_token': token, 'code': code}, format='json').status_code == 400
        fresh = login(c).json()['mfa_token']
        assert c.post('/api/auth/login/mfa/', {'mfa_token': fresh, 'code': code}, format='json').status_code == 400

    def test_challenge_locks_after_too_many_attempts(self, alice):
        secret, _ = _enable_mfa(alice)
        c = APIClient()
        token = login(c).json()['mfa_token']
        for _ in range(security.MFA_MAX_ATTEMPTS):
            c.post('/api/auth/login/mfa/', {'mfa_token': token, 'code': '000000'}, format='json')
        alice.mfa.refresh_from_db()
        ok = _next_code(secret, alice.mfa)
        assert c.post('/api/auth/login/mfa/', {'mfa_token': token, 'code': ok}, format='json').status_code == 400

    def test_forged_or_expired_challenge_rejected(self, alice):
        _enable_mfa(alice)
        forged = signing.dumps({'uid': alice.pk, 'n': 'x'}, salt='something-else')
        r = APIClient().post('/api/auth/login/mfa/', {'mfa_token': forged, 'code': '000000'}, format='json')
        assert r.status_code == 400

    def test_recovery_code_works_once(self, alice):
        _, codes = _enable_mfa(alice)
        c = APIClient()
        token = login(c).json()['mfa_token']
        assert c.post('/api/auth/login/mfa/', {'mfa_token': token, 'code': codes[0]}, format='json').status_code == 200
        token = login(c).json()['mfa_token']
        assert c.post('/api/auth/login/mfa/', {'mfa_token': token, 'code': codes[0]}, format='json').status_code == 400

    def test_disable_needs_password_and_code(self, alice):
        secret, _ = _enable_mfa(alice)
        c = APIClient()
        c.force_authenticate(alice)
        assert c.post('/api/auth/mfa/disable/', {'password': PASSWORD, 'code': '000000'},
                      format='json').status_code == 400
        alice.mfa.refresh_from_db()
        r = c.post('/api/auth/mfa/disable/', {'password': PASSWORD, 'code': _next_code(secret, alice.mfa)},
                   format='json')
        assert r.status_code == 200 and not MFADevice.objects.filter(user=alice).exists()

    def test_enabling_signs_out_other_devices(self, alice):
        other = APIClient()
        login(other)
        secret, _ = security.begin_setup(alice)
        c = APIClient()
        c.force_authenticate(alice)
        c.post('/api/auth/mfa/enable/', {'code': pyotp.TOTP(secret).now()}, format='json')
        assert other.post('/api/auth/token/refresh/').status_code == 401


# ── Email verification ───────────────────────────────────────────────────────

class TestEmailVerification:
    @pytest.mark.django_db(transaction=True)
    def test_register_sends_a_link_that_verifies(self):
        with override_settings(FRONTEND_URL='https://andromeda.test'):
            r = APIClient().post('/api/auth/register/', {
                'username': 'zola', 'email': 'zola@example.com', 'first_name': 'Zola', 'last_name': 'B',
                'password': PASSWORD, 'password2': PASSWORD, 'accept_terms': True}, format='json')
        assert r.status_code == 201 and r.json()['user']['email_verified'] is False
        body = mail.outbox[-1].body
        token = body.split('token=')[1].split()[0]
        assert APIClient().post('/api/auth/email/verify/', {'token': token}, format='json').status_code == 200
        from django.contrib.auth import get_user_model
        assert get_user_model().objects.get(username='zola').email_verified

    def test_link_for_an_old_address_is_rejected(self, alice):
        token = security.email_token(alice)
        alice.email = 'new@example.com'
        alice.save()
        assert APIClient().post('/api/auth/email/verify/', {'token': token}, format='json').status_code == 400

    def test_tampered_token_rejected(self, alice):
        token = security.email_token(alice)[:-2] + 'xx'
        assert APIClient().post('/api/auth/email/verify/', {'token': token}, format='json').status_code == 400

    def test_users_cannot_set_verification_or_badge_themselves(self, alice):
        c = APIClient()
        c.force_authenticate(alice)
        c.patch('/api/auth/me/', {'email_verified': True, 'is_verified': True}, format='json')
        alice.refresh_from_db()
        assert not alice.email_verified and not alice.is_verified


def test_ai_opt_out_removes_content_from_the_index(alice):
    from posts.models import Post
    from retrieval.models import Embedding
    p = Post.objects.create(author=alice, content='hello')
    Embedding.objects.create(kind='posts', object_id=p.id, text='hello', content_hash='x', vector=[0.0] * 1536,
                             model='fake')
    c = APIClient()
    c.force_authenticate(alice)
    with pytest.MonkeyPatch.context():
        assert c.patch('/api/auth/me/', {'ai_opt_out': True}, format='json').status_code == 200
    from retrieval.tasks import apply_ai_opt_out
    apply_ai_opt_out(alice.id)
    assert not Embedding.objects.filter(kind='posts', object_id=p.id).exists()
    from retrieval import documents
    assert documents.load('posts', p.id) is None
