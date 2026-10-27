"""
Populate a development database with a realistic social graph.

    python manage.py seed --users 200

Every seeded account shares one password, so the command refuses to run
unless DEBUG is on (or --i-know-this-is-not-production is passed).
"""
import random

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from chats.models import ChatMember, ChatRoom, Message
from groups.models import Group, GroupMember
from marketplace.models import Category, Listing
from pages.models import Page, PageFollow
from posts.models import Comment, Like, Post
from users.models import FriendRequest

FIRST = ['Thandi', 'Sipho', 'Lerato', 'Pieter', 'Ayanda', 'Johan', 'Naledi', 'Kabelo', 'Zanele',
         'Ruan', 'Nomsa', 'Tumelo', 'Anika', 'Bongani', 'Lindiwe', 'Musa', 'Karabo', 'Elsa']
LAST = ['Dlamini', 'Nkosi', 'van der Merwe', 'Mokoena', 'Botha', 'Naidoo', 'Khumalo', 'Pillay',
        'Mahlangu', 'Pretorius', 'Ndlovu', 'Smith', 'Molefe', 'Venter']
CITIES = ['Johannesburg', 'Cape Town', 'Durban', 'Pretoria', 'Gqeberha', 'Bloemfontein']
TOPICS = ['running', 'braai', 'rugby', 'coding', 'hiking', 'photography', 'jazz', 'gardening', 'coffee']
POSTS = [
    'Anyone keen for a {t} meetup this weekend in {c}?',
    'Finally got into {t}. Any tips for a beginner?',
    'Best {t} spot in {c}? Asking for a friend.',
    'Load shedding ruined my {t} plans again 😩',
    'Throwback to last summer, {t} all day.',
    'Looking for people into {t} near {c}.',
]
LISTINGS = [('Couch, 3-seater', 2500), ('Mountain bike', 4800), ('Gaming chair', 1500),
            ('Coffee machine', 1900), ('Desk lamp', 250), ('Bookshelf', 900), ('Camera lens', 6500)]


class Command(BaseCommand):
    help = 'Seed the database with demo users, friendships, posts, groups, chats and listings.'

    def add_arguments(self, parser):
        parser.add_argument('--users', type=int, default=100)
        parser.add_argument('--password', default='andromeda-demo-pass')
        parser.add_argument('--seed', type=int, default=42, help='Random seed for reproducible data')
        parser.add_argument('--i-know-this-is-not-production', action='store_true', dest='force')

    def handle(self, *args, users, password, seed, force, **options):
        if not settings.DEBUG and not force:
            raise CommandError('Refusing to seed with DEBUG off. Pass --i-know-this-is-not-production.')
        rng = random.Random(seed)
        with transaction.atomic():
            people = self._users(rng, users, password)
            self._friendships(rng, people)
            groups = self._groups(rng, people)
            self._posts(rng, people, groups)
            self._pages(rng, people)
            self._chats(rng, people)
            self._listings(rng, people)
        self.stdout.write(self.style.SUCCESS(
            f'Seeded {len(people)} users. Sign in as {people[0].username} / {password}'
        ))

    def _users(self, rng, n, password):
        User = get_user_model()
        start = User.objects.filter(username__startswith='demo').count()
        people = []
        for i in range(start, start + n):
            first, last = rng.choice(FIRST), rng.choice(LAST)
            u = User(
                username=f'demo{i}', email=f'demo{i}@example.test',
                first_name=first, last_name=last, location=rng.choice(CITIES),
                bio=f'Into {rng.choice(TOPICS)} and {rng.choice(TOPICS)}.',
                privacy_profile=rng.choices(['everyone', 'friends'], [8, 2])[0],
            )
            u.set_password(password)
            people.append(u)
        return User.objects.bulk_create(people)

    def _friendships(self, rng, people):
        pairs = set()
        for u in people:
            for v in rng.sample(people, k=min(len(people) - 1, rng.randint(3, 12))):
                if u.id != v.id:
                    pairs.add(tuple(sorted((u.id, v.id))))
        FriendRequest.objects.bulk_create(
            [FriendRequest(sender_id=a, receiver_id=b, status='accepted') for a, b in pairs],
            ignore_conflicts=True,
        )
        for u in people:
            u.friends_count = sum(1 for a, b in pairs if u.id in (a, b))
        get_user_model().objects.bulk_update(people, ['friends_count'])

    def _groups(self, rng, people):
        groups = []
        for topic in TOPICS:
            g = Group.objects.create(
                name=f'{rng.choice(CITIES)} {topic.title()} Club', description=f'All things {topic}.',
                privacy=rng.choices(['public', 'private'], [3, 1])[0], created_by=rng.choice(people),
            )
            members = {g.created_by, *rng.sample(people, k=min(len(people), rng.randint(5, 30)))}
            GroupMember.objects.bulk_create([
                GroupMember(group=g, user=m, role='admin' if m == g.created_by else 'member') for m in members
            ])
            g.members_count = len(members)
            g.save(update_fields=['members_count'])
            groups.append((g, list(members)))
        return groups

    def _posts(self, rng, people, groups):
        posts = []
        for u in people:
            for _ in range(rng.randint(1, 6)):
                text = rng.choice(POSTS).format(t=rng.choice(TOPICS), c=rng.choice(CITIES))
                posts.append(Post(author=u, content=text,
                                  privacy=rng.choices(['public', 'friends', 'private'], [6, 3, 1])[0]))
        for g, members in groups:
            for _ in range(rng.randint(3, 10)):
                posts.append(Post(author=rng.choice(members), group=g, content=f'Welcome to {g.name}!'))
        posts = Post.objects.bulk_create(posts)
        likes, comments = set(), []
        for p in rng.sample(posts, k=len(posts) // 2):
            for liker in rng.sample(people, k=min(len(people), rng.randint(1, 8))):
                likes.add((liker.id, p.id))
            for _ in range(rng.randint(0, 3)):
                comments.append(Comment(post=p, author=rng.choice(people), content='So true!'))
        Like.objects.bulk_create([Like(user_id=u, post_id=p) for u, p in likes], ignore_conflicts=True)
        Comment.objects.bulk_create(comments)
        for p in posts:
            p.likes_count = sum(1 for _, pid in likes if pid == p.id)
            p.comments_count = sum(1 for c in comments if c.post_id == p.id)
        Post.objects.bulk_update(posts, ['likes_count', 'comments_count'])
        for u in people:
            u.posts_count = sum(1 for p in posts if p.author_id == u.id)
        get_user_model().objects.bulk_update(people, ['posts_count'])

    def _pages(self, rng, people):
        for i, topic in enumerate(TOPICS[:5]):
            page = Page.objects.create(name=f'{topic.title()} SA', username=f'{topic}-sa-{rng.randint(100, 999)}-{i}',
                                       category='community', created_by=rng.choice(people))
            followers = rng.sample(people, k=min(len(people), rng.randint(5, 40)))
            PageFollow.objects.bulk_create([PageFollow(page=page, user=f) for f in followers])
            page.followers_count = len(followers)
            page.save(update_fields=['followers_count'])

    def _chats(self, rng, people):
        for u in rng.sample(people, k=min(len(people), 20)):
            other = rng.choice([p for p in people if p != u])
            room = ChatRoom.objects.create(room_type='direct', created_by=u)
            ChatMember.objects.bulk_create([ChatMember(room=room, user=u, role='admin'),
                                            ChatMember(room=room, user=other)])
            Message.objects.bulk_create([
                Message(room=room, sender=rng.choice([u, other]), content=line)
                for line in ('Hey!', 'Howzit?', 'Still on for Saturday?', 'Sharp, see you then.')
            ])

    def _listings(self, rng, people):
        cats = [Category.objects.get_or_create(slug=s, defaults={'name': n})[0]
                for s, n in [('furniture', 'Furniture'), ('electronics', 'Electronics'), ('sport', 'Sport')]]
        Listing.objects.bulk_create([
            Listing(seller=rng.choice(people), title=title, price=price, category=rng.choice(cats),
                    description=f'{title} in good condition.', location=rng.choice(CITIES),
                    condition='good', currency='ZAR')
            for title, price in LISTINGS for _ in range(3)
        ])
