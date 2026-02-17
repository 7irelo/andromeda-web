import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

User = get_user_model()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="alice",
        email="alice@example.com",
        password="testpass123",
        first_name="Alice",
        last_name="Smith",
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        username="bob",
        email="bob@example.com",
        password="testpass123",
        first_name="Bob",
        last_name="Jones",
    )


@pytest.fixture
def auth_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegister:
    def test_register_creates_user(self, api_client, db):
        url = reverse("register")
        payload = {
            "username": "charlie",
            "email": "charlie@example.com",
            "first_name": "Charlie",
            "last_name": "Brown",
            "password": "securepass99",
            "password2": "securepass99",
        }
        response = api_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert User.objects.filter(username="charlie").exists()
        assert "tokens" in response.data
        assert "access" in response.data["tokens"]

    def test_register_password_mismatch(self, api_client, db):
        url = reverse("register")
        payload = {
            "username": "dave",
            "email": "dave@example.com",
            "first_name": "Dave",
            "last_name": "D",
            "password": "pass1234",
            "password2": "different",
        }
        response = api_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_duplicate_username(self, api_client, user):
        url = reverse("register")
        payload = {
            "username": user.username,
            "email": "new@example.com",
            "first_name": "X",
            "last_name": "Y",
            "password": "testpass123",
            "password2": "testpass123",
        }
        response = api_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ── Login ─────────────────────────────────────────────────────────────────────

class TestLogin:
    def test_login_returns_tokens(self, api_client, user):
        url = reverse("login")
        response = api_client.post(url, {"username": "alice", "password": "testpass123"})
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        assert "refresh" in response.data

    def test_login_wrong_password(self, api_client, user):
        url = reverse("login")
        response = api_client.post(url, {"username": "alice", "password": "wrong"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ── Me endpoint ───────────────────────────────────────────────────────────────

class TestMe:
    def test_me_returns_current_user(self, auth_client, user):
        response = auth_client.get(reverse("me"))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["username"] == user.username

    def test_me_unauthenticated(self, api_client):
        response = api_client.get(reverse("me"))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_me_update_bio(self, auth_client, user):
        response = auth_client.patch(reverse("me"), {"bio": "Hello world"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.bio == "Hello world"


# ── Follow ────────────────────────────────────────────────────────────────────

class TestFollow:
    def test_follow_user(self, auth_client, user, other_user):
        url = reverse("follow", kwargs={"user_id": other_user.id})
        response = auth_client.post(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["following"] is True

    def test_unfollow_user(self, auth_client, user, other_user):
        from users.models import Follow
        Follow.objects.create(follower=user, following=other_user)
        url = reverse("follow", kwargs={"user_id": other_user.id})
        response = auth_client.delete(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["following"] is False

    def test_cannot_follow_self(self, auth_client, user):
        url = reverse("follow", kwargs={"user_id": user.id})
        response = auth_client.post(url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ── Friend requests ───────────────────────────────────────────────────────────

class TestFriendRequests:
    def test_send_friend_request(self, auth_client, user, other_user):
        url = reverse("friend-request-list")
        response = auth_client.post(url, {"receiver_id": other_user.id}, format="json")
        assert response.status_code == status.HTTP_201_CREATED

    def test_accept_friend_request(self, api_client, user, other_user):
        from users.models import FriendRequest
        fr = FriendRequest.objects.create(sender=other_user, receiver=user)
        api_client.force_authenticate(user=user)
        url = reverse("friend-request-accept", kwargs={"pk": fr.id})
        response = api_client.post(url)
        assert response.status_code == status.HTTP_200_OK
        fr.refresh_from_db()
        assert fr.status == FriendRequest.STATUS_ACCEPTED
