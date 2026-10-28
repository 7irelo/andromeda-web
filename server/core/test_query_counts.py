"""
Query budgets for the main list endpoints.

Each test loads a list page, adds more rows of the same shape, and loads it
again: the number of queries must not grow with the number of rows (no N+1),
and must stay under a fixed ceiling. When an endpoint legitimately needs a
new query, raise its ceiling here in the same change.
"""
import itertools
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

from chats.models import ChatMember, ChatRoom, Message
from groups.models import Group, GroupMember
from marketplace.models import Category, Listing
from notifications.models import Notification
from pages.models import Page, PageFollow
from posts.models import Comment, Like, Post
from users.models import FriendRequest

User = get_user_model()
_seq = itertools.count()


def _user(prefix='u'):
    n = next(_seq)
    return User.objects.create_user(username=f'{prefix}{n}', password='pass-1234567', email=f'{prefix}{n}@x.io',
                                    first_name='Search', last_name=f'Person{n}')


def count(client, url):
    with CaptureQueriesContext(connection) as ctx:
        resp = client.get(url)
    assert resp.status_code == 200, resp.content[:300]
    return len(ctx.captured_queries), resp


def assert_flat(client, url, grow, ceiling, rows=None):
    """Queries for ``url`` must not change after ``grow()`` adds rows, and stay <= ``ceiling``."""
    before, first = count(client, url)
    grow()
    after, second = count(client, url)
    if rows is not None:
        assert rows(second) > rows(first), 'the second page should have more rows'
    assert after == before, f'{url}: {before} queries with fewer rows, {after} with more (N+1?)'
    assert after <= ceiling, f'{url}: {after} queries, budget {ceiling}'


@pytest.fixture
def me(db):
    return _user('me')


@pytest.fixture
def client(me):
    c = APIClient()
    c.force_authenticate(me)
    return c


def _results(resp):
    data = resp.data
    return len(data['results'] if isinstance(data, dict) and 'results' in data else data)


class TestQueryBudgets:
    def test_home_feed(self, client, me):
        group = Group.objects.create(name='G', created_by=me)
        GroupMember.objects.create(group=group, user=me, role='admin')
        page = Page.objects.create(name='P', username='pq', created_by=me)
        PageFollow.objects.create(page=page, user=me)

        def grow(n=3):
            for _ in range(n):
                friend = _user('f')
                FriendRequest.objects.create(sender=me, receiver=friend, status=FriendRequest.STATUS_ACCEPTED)
                original = Post.objects.create(author=friend, content='original')
                Post.objects.create(author=friend, content='share', shared_post=original)
                Post.objects.create(author=friend, content='in group', group=group)
                Post.objects.create(author=friend, content='as page', page=page)
                Like.objects.create(user=me, post=original)
                Comment.objects.create(post=original, author=friend, content='c')

        grow(1)
        for sort in ('top', 'latest'):
            assert_flat(client, f'/api/posts/?feed=true&sort={sort}', lambda: grow(1), ceiling=24, rows=_results)

    def test_group_feed(self, client, me):
        group = Group.objects.create(name='G', created_by=me, privacy='public')
        GroupMember.objects.create(group=group, user=me, role='admin')

        def grow(n=3):
            for _ in range(n):
                author = _user('g')
                GroupMember.objects.create(group=group, user=author)
                post = Post.objects.create(author=author, content='hello group', group=group)
                Like.objects.create(user=me, post=post)

        grow()
        assert_flat(client, f'/api/posts/?group={group.id}', grow, ceiling=10, rows=_results)

    def test_notifications(self, client, me):
        def grow(n=3):
            for _ in range(n):
                Notification.objects.create(recipient=me, sender=_user('n'), notification_type='like',
                                            title='liked your post')

        grow()
        assert_flat(client, reverse('notification-list'), grow, ceiling=7, rows=_results)

    def test_chat_rooms(self, client, me):
        def grow(n=3):
            for _ in range(n):
                other = _user('c')
                room = ChatRoom.objects.create(room_type=ChatRoom.TYPE_DIRECT, created_by=me)
                ChatMember.objects.create(room=room, user=me)
                ChatMember.objects.create(room=room, user=other)
                Message.objects.create(room=room, sender=other, content='hi')

        grow()
        assert_flat(client, reverse('chatroom-list'), grow, ceiling=6, rows=_results)

    def test_listings(self, client, me):
        category = Category.objects.create(name='Bikes', slug='bikes')

        def grow(n=3):
            for _ in range(n):
                Listing.objects.create(seller=_user('s'), title='Bike', description='A bike',
                                       price=Decimal('10.00'), category=category)

        grow()
        assert_flat(client, reverse('listing-list'), grow, ceiling=10, rows=_results)

    def test_search(self, client, me):
        def grow(n=2):
            for _ in range(n):
                person = _user('s')
                FriendRequest.objects.create(sender=person, receiver=me)
                Post.objects.create(author=person, content='Search me')
                Listing.objects.create(seller=person, title='Search bike', description='d', price=Decimal('1'))
                group = Group.objects.create(name='Search club', created_by=person, privacy='public')
                GroupMember.objects.create(group=group, user=me)
                page = Page.objects.create(name='Search page', username=f'sp{person.id}', created_by=person)
                PageFollow.objects.create(page=page, user=me)

        grow()

        def rows(resp):
            return sum(len(v) for v in resp.data['results'].values())

        assert_flat(client, reverse('search') + '?q=search', grow, ceiling=30, rows=rows)
