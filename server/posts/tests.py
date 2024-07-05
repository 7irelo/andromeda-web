import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from posts.models import Post, Like, Comment

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="alice", password="pass", email="a@a.com")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(username="bob", password="pass", email="b@b.com")


@pytest.fixture
def auth_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def post(user):
    return Post.objects.create(author=user, content="Hello world", post_type=Post.TYPE_TEXT)


# ── CRUD ──────────────────────────────────────────────────────────────────────

class TestPostCRUD:
    def test_create_post(self, auth_client):
        url = reverse("post-list")
        response = auth_client.post(url, {"content": "My first post", "post_type": "text"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["content"] == "My first post"

    def test_create_post_unauthenticated(self, api_client):
        url = reverse("post-list")
        response = api_client.post(url, {"content": "x"}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_posts(self, auth_client, post):
        url = reverse("post-list")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] >= 1

    def test_retrieve_post(self, auth_client, post):
        url = reverse("post-detail", kwargs={"pk": post.id})
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == post.id

    def test_update_own_post(self, auth_client, post):
        url = reverse("post-detail", kwargs={"pk": post.id})
        response = auth_client.patch(url, {"content": "Updated"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["content"] == "Updated"
        assert response.data["is_edited"] is True

    def test_delete_own_post(self, auth_client, post):
        url = reverse("post-detail", kwargs={"pk": post.id})
        response = auth_client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Post.objects.filter(pk=post.id).exists()

    def test_cannot_delete_other_users_post(self, api_client, other_user, post):
        api_client.force_authenticate(user=other_user)
        url = reverse("post-detail", kwargs={"pk": post.id})
        response = api_client.delete(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ── Reactions ─────────────────────────────────────────────────────────────────

class TestReactions:
    def test_like_post(self, auth_client, post):
        url = reverse("post-react", kwargs={"pk": post.id})
        response = auth_client.post(url, {"reaction": "like"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["reacted"] is True
        assert Like.objects.filter(post=post).count() == 1

    def test_unlike_post(self, auth_client, user, post):
        Like.objects.create(user=user, post=post, reaction="like")
        url = reverse("post-react", kwargs={"pk": post.id})
        response = auth_client.post(url, {"reaction": "like"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["reacted"] is False
        assert Like.objects.filter(post=post).count() == 0

    def test_change_reaction(self, auth_client, user, post):
        Like.objects.create(user=user, post=post, reaction="like")
        url = reverse("post-react", kwargs={"pk": post.id})
        response = auth_client.post(url, {"reaction": "love"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["reaction"] == "love"


# ── Comments ──────────────────────────────────────────────────────────────────

class TestComments:
    def test_add_comment(self, auth_client, post):
        url = reverse("post-comments", kwargs={"pk": post.id})
        response = auth_client.post(url, {"content": "Nice post!"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert Comment.objects.filter(post=post).count() == 1

    def test_list_comments(self, auth_client, user, post):
        Comment.objects.create(post=post, author=user, content="First")
        Comment.objects.create(post=post, author=user, content="Second")
        url = reverse("post-comments", kwargs={"pk": post.id})
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2

    def test_comment_increments_counter(self, auth_client, post):
        url = reverse("post-comments", kwargs={"pk": post.id})
        auth_client.post(url, {"content": "Comment"}, format="json")
        post.refresh_from_db()
        assert post.comments_count == 1


# ── Feed ──────────────────────────────────────────────────────────────────────

class TestFeed:
    def test_feed_shows_followed_user_posts(self, api_client, user, other_user):
        from users.models import Follow
        Follow.objects.create(follower=user, following=other_user)
        Post.objects.create(author=other_user, content="Bob's post", privacy="public")
        api_client.force_authenticate(user=user)
        response = api_client.get(reverse("post-list") + "?feed=true")
        assert response.status_code == status.HTTP_200_OK
        usernames = [p["author"]["username"] for p in response.data["results"]]
        assert "bob" in usernames

    def test_feed_excludes_unfollowed_users(self, api_client, user, other_user):
        Post.objects.create(author=other_user, content="Stranger's post", privacy="public")
        api_client.force_authenticate(user=user)
        response = api_client.get(reverse("post-list") + "?feed=true")
        assert response.status_code == status.HTTP_200_OK
        usernames = [p["author"]["username"] for p in response.data["results"]]
        assert "bob" not in usernames


class TestPostSearch:
    def test_search_matches_post_content(self, auth_client, user):
        match = Post.objects.create(author=user, content="Exploring the Andromeda galaxy")
        other = Post.objects.create(author=user, content="Weekend cooking update")

        response = auth_client.get(reverse("post-list") + "?search=andromeda")

        assert response.status_code == status.HTTP_200_OK
        result_ids = [p["id"] for p in response.data["results"]]
        assert match.id in result_ids
        assert other.id not in result_ids

    def test_search_matches_author_fields(self, auth_client, other_user):
        bob_post = Post.objects.create(author=other_user, content="Author lookup test")

        response = auth_client.get(reverse("post-list") + "?search=Bob")

        assert response.status_code == status.HTTP_200_OK
        result_ids = [p["id"] for p in response.data["results"]]
        assert bob_post.id in result_ids
