"""
Marketplace: listing management, saved listings and price drops, reviews,
filters (category tree, condition, price, distance, full-text) and the
Listing Assistant. Authorization cases follow core/test_security.py: owner,
stranger, blocked user and anonymous.
"""
import base64
import io
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from core import ai_client
from notifications.models import Notification
from users.models import Block

from . import geo, pricing
from .models import Category, Listing, ListingLike, Review

User = get_user_model()
PASSWORD = 'correct-horse-battery'


def make_user(name):
    return User.objects.create_user(username=name, email=f'{name}@example.com', password=PASSWORD)


def client_for(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.fixture(autouse=True)
def _fresh_cache():
    cache.clear()


@pytest.fixture
def alice(db):
    return make_user('alice')


@pytest.fixture
def bob(db):
    return make_user('bob')


@pytest.fixture
def mallory(db):
    return make_user('mallory')


@pytest.fixture
def tree(db):
    electronics = Category.objects.create(name='Electronics', slug='electronics')
    phones = Category.objects.create(name='Phones', slug='phones', parent=electronics)
    furniture = Category.objects.create(name='Furniture', slug='furniture')
    return {'electronics': electronics, 'phones': phones, 'furniture': furniture}


def listing(seller, title='Couch', price=100, **kw):
    return Listing.objects.create(seller=seller, title=title, description=kw.pop('description', 'Nice.'),
                                  price=price, **kw)


def detail(pk):
    return reverse('listing-detail', kwargs={'pk': pk})


def ids(response):
    return [x['id'] for x in response.data['results']]


def jpeg(size=(40, 30), exif=False):
    img = Image.new('RGB', size, 'blue')
    buf = io.BytesIO()
    kwargs = {}
    if exif:
        e = Image.Exif()
        e[0x010F] = 'SpyCam'
        kwargs['exif'] = e
    img.save(buf, format='JPEG', **kwargs)
    return SimpleUploadedFile('photo.jpg', buf.getvalue(), content_type='image/jpeg')


# ── Authorization ────────────────────────────────────────────────────────────

class TestAuthorization:
    @pytest.mark.parametrize('name,kwargs', [
        ('listing-list', {}), ('listing-saved', {}), ('listing-mine-counts', {}), ('listing-draft', {}),
        ('category-list', {}), ('marketplace-cities', {}), ('marketplace-seller', {'pk': 1}),
    ])
    def test_anonymous_is_rejected(self, db, name, kwargs):
        c = APIClient()
        url = reverse(name, kwargs=kwargs)
        assert (c.post(url) if name == 'listing-draft' else c.get(url)).status_code == 401

    def test_owner_can_edit_and_change_status(self, alice):
        item = listing(alice)
        c = client_for(alice)
        r = c.patch(detail(item.pk), {'title': 'Leather couch', 'status': 'reserved'}, format='json')
        assert r.status_code == 200 and r.data['status'] == 'reserved' and r.data['title'] == 'Leather couch'

    def test_stranger_cannot_edit_or_delete(self, alice, mallory):
        item = listing(alice)
        c = client_for(mallory)
        assert c.patch(detail(item.pk), {'status': 'sold'}, format='json').status_code == 403
        assert c.delete(detail(item.pk)).status_code == 403
        assert c.post(reverse('listing-upload-images', kwargs={'pk': item.pk}),
                      {'images': [jpeg()]}, format='multipart').status_code == 403
        item.refresh_from_db()
        assert item.status == 'active'

    def test_blocked_user_cannot_see_save_or_review(self, alice, mallory):
        item = listing(alice)
        Block.objects.create(blocker=alice, blocked=mallory)
        c = client_for(mallory)
        assert c.get(detail(item.pk)).status_code == 404
        assert c.post(reverse('listing-like', kwargs={'pk': item.pk})).status_code == 404
        assert c.post(reverse('listing-reviews', kwargs={'pk': item.pk}), {'rating': 1}).status_code == 404
        assert item.pk not in ids(c.get(reverse('listing-list')))
        assert c.get(reverse('marketplace-seller', kwargs={'pk': alice.pk})).status_code == 404

    def test_block_hides_both_ways(self, alice, mallory):
        item = listing(mallory)
        Block.objects.create(blocker=alice, blocked=mallory)
        assert client_for(alice).get(detail(item.pk)).status_code == 404

    def test_moderation_fields_cannot_be_written(self, alice):
        item = listing(alice, moderation_status='removed')
        client_for(alice).patch(detail(item.pk), {'moderation_status': 'ok', 'views_count': 999}, format='json')
        item.refresh_from_db()
        assert item.moderation_status == 'removed' and item.views_count == 0

    def test_editing_text_is_moderated_again(self, alice):
        item = listing(alice)
        with mock.patch('marketplace.views.queue_moderation') as q:
            client_for(alice).patch(detail(item.pk), {'price': 90}, format='json')
            q.assert_not_called()
            client_for(alice).patch(detail(item.pk), {'description': 'Pay a deposit first'}, format='json')
            q.assert_called_once_with('listing', item.pk)


# ── Status and My listings ───────────────────────────────────────────────────

class TestMyListings:
    def test_reserved_is_public_but_sold_and_draft_are_not(self, alice, bob):
        active, reserved = listing(alice), listing(alice, status='reserved')
        sold, draft = listing(alice, status='sold'), listing(alice, status='draft')
        c = client_for(bob)
        assert set(ids(c.get(reverse('listing-list')))) == {active.pk, reserved.pk}
        assert c.get(detail(sold.pk)).status_code == 404
        assert c.get(detail(draft.pk)).status_code == 404
        assert client_for(alice).get(detail(sold.pk)).status_code == 200

    def test_mine_filters_by_status_and_counts(self, alice, bob):
        listing(alice)
        listing(alice, status='reserved')
        sold = listing(alice, status='sold')
        listing(bob)
        c = client_for(alice)
        assert ids(c.get(reverse('listing-list') + '?mine=true&status=sold')) == [sold.pk]
        assert len(ids(c.get(reverse('listing-list') + '?mine=true'))) == 3
        assert c.get(reverse('listing-list') + '?mine=true&status=bogus').status_code == 400
        counts = c.get(reverse('listing-mine-counts')).data
        assert counts == {'active': 1, 'reserved': 1, 'sold': 1, 'draft': 0, 'all': 3}

    def test_other_users_mine_is_never_exposed(self, alice, bob):
        listing(alice, status='draft')
        assert ids(client_for(bob).get(reverse('listing-list') + '?mine=true')) == []


# ── Saved listings and price drops ───────────────────────────────────────────

class TestSaved:
    def test_save_toggle_and_saved_page(self, alice, bob):
        item = listing(alice)
        c = client_for(bob)
        assert c.post(reverse('listing-like', kwargs={'pk': item.pk})).data == {'liked': True}
        r = c.get(reverse('listing-saved'))
        assert ids(r) == [item.pk] and r.data['results'][0]['is_liked'] is True
        assert c.post(reverse('listing-like', kwargs={'pk': item.pk})).data == {'liked': False}
        assert ids(c.get(reverse('listing-saved'))) == []

    def test_cannot_save_own_listing(self, alice):
        item = listing(alice)
        assert client_for(alice).post(reverse('listing-like', kwargs={'pk': item.pk})).status_code == 400

    def test_saved_page_drops_listings_that_became_invisible(self, alice, bob, mallory):
        sold, blocked, ok = listing(alice), listing(mallory), listing(alice)
        for item in (sold, blocked, ok):
            ListingLike.objects.create(user=bob, listing=item)
        Listing.objects.filter(pk=sold.pk).update(status='sold')
        Block.objects.create(blocker=mallory, blocked=bob)
        assert ids(client_for(bob).get(reverse('listing-saved'))) == [ok.pk]

    def test_price_drop_notifies_savers_only(self, alice, bob, mallory, django_capture_on_commit_callbacks):
        item = listing(alice, price=500)
        carol = make_user('carol')
        make_user('dave')  # didn't save it
        for u in (bob, mallory, carol):
            ListingLike.objects.create(user=u, listing=item)
        Block.objects.create(blocker=mallory, blocked=alice)
        with django_capture_on_commit_callbacks(execute=True):
            r = client_for(alice).patch(detail(item.pk), {'price': '400.00'}, format='json')
        assert r.status_code == 200
        notes = Notification.objects.filter(extra__kind='price_drop')
        assert sorted(n.recipient.username for n in notes) == ['bob', 'carol']
        n = notes.first()
        assert n.notification_type == Notification.TYPE_SYSTEM and n.extra['listing_id'] == item.pk
        assert n.extra['old_price'] == '500.00' and n.extra['new_price'] == '400.00'

    def test_price_rise_or_same_price_is_silent(self, alice, bob, django_capture_on_commit_callbacks):
        item = listing(alice, price=500)
        ListingLike.objects.create(user=bob, listing=item)
        with django_capture_on_commit_callbacks(execute=True):
            client_for(alice).patch(detail(item.pk), {'price': '600'}, format='json')
            client_for(alice).patch(detail(item.pk), {'title': 'Same price'}, format='json')
        assert not Notification.objects.exists()

    def test_price_drop_respects_marketplace_preferences(self, alice, bob, django_capture_on_commit_callbacks):
        from notifications.models import NotificationPreference
        NotificationPreference.objects.create(
            user=bob, channels={'marketplace': {'in_app': False, 'push': False, 'email': False}})
        item = listing(alice, price=500)
        ListingLike.objects.create(user=bob, listing=item)
        with django_capture_on_commit_callbacks(execute=True):
            client_for(alice).patch(detail(item.pk), {'price': '400'}, format='json')
        assert not Notification.objects.exists()

    def test_no_price_drop_for_hidden_listing(self, alice, bob):
        from .tasks import notify_price_drop
        item = listing(alice, price=300, status='sold')
        ListingLike.objects.create(user=bob, listing=item)
        assert notify_price_drop(item.pk, '500') == 0


# ── Reviews and ratings ──────────────────────────────────────────────────────

class TestReviews:
    def test_ratings_are_aggregated_on_listing_and_seller(self, alice, bob, mallory):
        a, b = listing(alice), listing(alice, title='Table')
        Review.objects.create(listing=a, reviewer=bob, rating=5)
        Review.objects.create(listing=a, reviewer=mallory, rating=4)
        Review.objects.create(listing=b, reviewer=bob, rating=3)
        r = client_for(bob).get(detail(a.pk))
        assert r.data['rating'] == {'average': 4.5, 'count': 2}
        assert r.data['seller_rating'] == {'average': 4.0, 'count': 3}
        rows = {x['id']: x for x in client_for(bob).get(reverse('listing-list')).data['results']}
        assert rows[b.pk]['rating'] == {'average': 3.0, 'count': 1}
        assert rows[b.pk]['seller_rating']['count'] == 3
        seller = client_for(bob).get(reverse('marketplace-seller', kwargs={'pk': alice.pk})).data
        assert seller['rating'] == {'average': 4.0, 'count': 3} and len(seller['reviews']) == 3

    def test_unrated_listing(self, alice, bob):
        r = client_for(bob).get(detail(listing(alice).pk))
        assert r.data['rating'] == {'average': None, 'count': 0}

    def test_list_aggregates_do_not_scale_with_rows(self, alice, bob):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        for i in range(8):
            item = listing(alice, title=f'Item {i}')
            Review.objects.create(listing=item, reviewer=bob, rating=4)
            ListingLike.objects.create(user=bob, listing=item)
        with CaptureQueriesContext(connection) as ctx:
            client_for(bob).get(reverse('listing-list'))
        # Ratings and the saved flag ride along in the page query as subqueries.
        touching = [q for q in ctx.captured_queries
                    if 'marketplace_reviews' in q['sql'] or 'marketplace_likes' in q['sql']]
        assert len(touching) == 1

    def test_review_rules(self, alice, bob):
        item = listing(alice)
        url = reverse('listing-reviews', kwargs={'pk': item.pk})
        assert client_for(alice).post(url, {'rating': 5}).status_code == 403
        assert client_for(bob).post(url, {'rating': 9}).status_code == 400
        assert client_for(bob).post(url, {'rating': 4, 'comment': 'Smooth sale'}).status_code == 201
        assert client_for(bob).post(url, {'rating': 5}).status_code == 400

    def test_blocked_reviewers_are_hidden(self, alice, bob, mallory):
        item = listing(alice)
        Review.objects.create(listing=item, reviewer=mallory, rating=1, comment='spite')
        Review.objects.create(listing=item, reviewer=bob, rating=5)
        Block.objects.create(blocker=bob, blocked=mallory)
        r = client_for(bob).get(reverse('listing-reviews', kwargs={'pk': item.pk}))
        assert [x['reviewer']['username'] for x in r.data] == ['bob']
        seller = client_for(bob).get(reverse('marketplace-seller', kwargs={'pk': alice.pk})).data
        assert [x['reviewer']['username'] for x in seller['reviews']] == ['bob']


# ── Filters, search and distance ─────────────────────────────────────────────

class TestFilters:
    def test_category_tree(self, alice, tree):
        r = client_for(alice).get(reverse('category-list'))
        top = {c['slug']: c for c in r.data}
        assert set(top) == {'electronics', 'furniture'}
        assert [c['slug'] for c in top['electronics']['children']] == ['phones']

    def test_category_includes_descendants(self, alice, bob, tree):
        phone = listing(alice, title='Phone', category=tree['phones'])
        listing(alice, title='Chair', category=tree['furniture'])
        c = client_for(bob)
        assert ids(c.get(reverse('listing-list') + '?category=electronics')) == [phone.pk]
        assert ids(c.get(reverse('listing-list') + '?category=nope')) == []

    def test_condition_and_price(self, alice, bob):
        cheap = listing(alice, price=50, condition='new')
        listing(alice, price=500, condition='new')
        listing(alice, price=60, condition='poor')
        c = client_for(bob)
        assert ids(c.get(reverse('listing-list') + '?condition=new,like_new&max_price=100')) == [cheap.pk]
        assert c.get(reverse('listing-list') + '?condition=mint').status_code == 400
        assert c.get(reverse('listing-list') + '?min_price=abc').status_code == 400
        assert c.get(reverse('listing-list') + '?max_price=NaN').status_code == 400

    def test_sorting(self, alice, bob):
        a, b, c_ = listing(alice, price=30), listing(alice, price=10), listing(alice, price=20)
        c = client_for(bob)
        assert ids(c.get(reverse('listing-list') + '?sort=price_asc')) == [b.pk, c_.pk, a.pk]
        assert ids(c.get(reverse('listing-list') + '?sort=price_desc')) == [a.pk, c_.pk, b.pk]
        assert ids(c.get(reverse('listing-list') + '?sort=newest')) == [c_.pk, b.pk, a.pk]
        assert c.get(reverse('listing-list') + '?sort=price;drop').status_code == 400

    def test_full_text_search_over_title_and_description(self, alice, bob):
        by_title = listing(alice, title='Mountain bike')
        by_desc = listing(alice, title='Bicycle', description='Great mountain trail ride')
        listing(alice, title='Sofa')
        r = client_for(bob).get(reverse('listing-list') + '?search=mountain')
        assert set(ids(r)) == {by_title.pk, by_desc.pk}

    def test_location_text_sets_city_centroid(self, alice):
        r = client_for(alice).post(reverse('listing-list'), {'title': 'Desk', 'description': 'Oak', 'price': 10,
                                                             'location': 'Sea Point, Cape Town'})
        assert r.status_code == 201, r.data
        item = Listing.objects.get(pk=r.data['id'])
        assert (item.latitude, item.longitude) == (round(-33.9249, 2), round(18.4241, 2))

    def test_precise_position_is_snapped_and_hidden_from_others(self, alice, bob):
        r = client_for(alice).post(reverse('listing-list'), {
            'title': 'Desk', 'description': 'Oak', 'price': 10, 'location': 'Cape Town',
            'latitude': -33.918861, 'longitude': 18.423300}, format='json')
        item = Listing.objects.get(pk=r.data['id'])
        assert (item.latitude, item.longitude) == (-33.92, 18.42)  # never stored precisely
        assert 'latitude' not in r.data and r.data['approx_point'] == {'latitude': -33.92, 'longitude': 18.42}
        other = client_for(bob).get(detail(item.pk)).data
        assert other['approx_point'] == {'latitude': -33.9, 'longitude': 18.4}
        assert 'latitude' not in other and 'longitude' not in other

    def test_half_a_coordinate_is_rejected(self, alice):
        r = client_for(alice).post(reverse('listing-list'), {'title': 'Desk', 'description': 'Oak', 'price': 10,
                                                             'latitude': -33.9}, format='json')
        assert r.status_code == 400

    def test_distance_filter_and_nearest_sort(self, alice, bob):
        jhb = listing(alice, title='JHB', latitude=-26.20, longitude=28.05)
        pta = listing(alice, title='PTA', latitude=-25.75, longitude=28.23)
        cpt = listing(alice, title='CPT', latitude=-33.92, longitude=18.42)
        listing(alice, title='Nowhere')
        c = client_for(bob)
        r = c.get(reverse('listing-list') + '?city=Johannesburg&radius_km=100&sort=nearest')
        assert ids(r) == [jhb.pk, pta.pk]
        assert r.data['results'][0]['distance_km'] == 1 and 50 <= r.data['results'][1]['distance_km'] <= 60
        r = c.get(reverse('listing-list') + '?lat=-33.9&lng=18.4&sort=nearest')
        assert ids(r)[:3] == [cpt.pk, jhb.pk, pta.pk]
        assert ids(r)[3:] and r.data['results'][3]['distance_km'] is None  # unknown location last

    def test_distance_params_are_validated(self, bob):
        c = client_for(bob)
        assert c.get(reverse('listing-list') + '?radius_km=10').status_code == 400
        assert c.get(reverse('listing-list') + '?sort=nearest').status_code == 400
        assert c.get(reverse('listing-list') + '?lat=95&lng=10').status_code == 400
        assert c.get(reverse('listing-list') + '?city=Atlantis').status_code == 400
        assert c.get(reverse('listing-list') + '?city=Durban&radius_km=9000').status_code == 400

    def test_haversine_matches_python(self):
        assert abs(geo.haversine_km(-26.2041, 28.0473, -33.9249, 18.4241) - 1262) < 5
        assert geo.city_for('Port Elizabeth') == 'Gqeberha'
        assert geo.city_for('Quigney, East London') == 'East London'
        assert geo.city_for('Somewhere') is None


# ── Listing Assistant ────────────────────────────────────────────────────────

def ai_draft(**draft):
    return mock.patch('core.ai_client.call', return_value={
        'draft': {'title': 'Samsung Galaxy S21 phone', 'description': 'Lightly used, with box.',
                  'category': 'phones', 'condition': 'like_new', **draft},
        'model': 'claude-sonnet-5-5', 'cost_usd': 0.004})


@pytest.fixture
def ai_on(settings):
    settings.AI_SERVICE_URL = 'http://ai.internal'
    settings.AI_SERVICE_SECRET = 's' * 40


def post_draft(user, images=None, **data):
    return client_for(user).post(reverse('listing-draft'), {'images': images or [jpeg()], **data},
                                 format='multipart')


class TestListingAssistant:
    def test_returns_editable_draft_with_category_and_images_sent(self, alice, tree, ai_on):
        with ai_draft() as call:
            r = post_draft(alice, images=[jpeg(exif=True), jpeg((3000, 2000))], hint='Galaxy S21, 128GB')
        assert r.status_code == 200, r.data
        assert r.data['title'] == 'Samsung Galaxy S21 phone' and r.data['ai_suggested'] is True
        assert r.data['category']['slug'] == 'phones' and r.data['condition'] == 'like_new'
        assert r.data['price_suggestion'] is None  # no comparables yet
        path, payload = call.call_args.args
        assert path == '/v1/listing/draft' and call.call_args.kwargs['user_id'] == alice.id
        assert payload['hint'] == 'Galaxy S21, 128GB'
        assert {'slug': 'phones', 'name': 'Electronics > Phones'} in payload['categories']
        assert len(payload['images']) == 2
        for part in payload['images']:
            assert part['media_type'] == 'image/jpeg'
            img = Image.open(io.BytesIO(base64.b64decode(part['data'])))
            assert max(img.size) <= 1568 and not img.getexif()
        assert not Listing.objects.exists()  # nothing is saved by drafting

    def test_unknown_category_or_condition_from_ai_is_nulled(self, alice, tree, ai_on):
        with ai_draft(category='weapons', condition='mint'):
            r = post_draft(alice)
        assert r.data['category'] is None and r.data['condition'] is None

    def test_rejects_non_images_and_too_many(self, alice, ai_on):
        evil = SimpleUploadedFile('evil.jpg', b'<?php system($_GET[1]); ?>', content_type='image/jpeg')
        with ai_draft() as call:
            assert post_draft(alice, images=[evil]).status_code == 400
            assert post_draft(alice, images=[jpeg() for _ in range(5)]).status_code == 400
            assert client_for(alice).post(reverse('listing-draft'), {}, format='multipart').status_code == 400
        call.assert_not_called()

    def test_ai_opt_out_is_respected(self, alice, ai_on):
        alice.ai_opt_out = True
        alice.save(update_fields=['ai_opt_out'])
        with ai_draft() as call:
            assert post_draft(alice).status_code == 403
        call.assert_not_called()

    def test_ai_unavailable_is_a_friendly_503(self, alice):
        r = post_draft(alice)  # AI service not configured
        assert r.status_code == 503 and 'not available' in r.data['detail']

    def test_ai_errors_are_mapped(self, alice, ai_on):
        with mock.patch('core.ai_client.call', side_effect=ai_client.AIUnavailable('down')):
            assert post_draft(alice).status_code == 503
        with mock.patch('core.ai_client.call', side_effect=ai_client.AIRejected(429, 'Daily AI allowance used up')):
            r = post_draft(alice)
            assert r.status_code == 429 and 'allowance' in r.data['detail']

    def test_uses_the_ai_throttle_scope(self, alice, ai_on):
        rates = {**ScopedRateThrottle.THROTTLE_RATES, 'ai': '1/min'}
        with mock.patch.object(ScopedRateThrottle, 'THROTTLE_RATES', rates), ai_draft():
            assert post_draft(alice).status_code == 200
            assert post_draft(alice).status_code == 429
            # Other marketplace endpoints don't share the AI allowance.
            assert client_for(alice).get(reverse('listing-list')).status_code == 200

    def test_price_suggestion_from_comparables(self, alice, bob, mallory, tree, ai_on):
        for price in (100, 200, 300, 400, 500):
            listing(bob, title='Samsung Galaxy S21 128GB', price=price, category=tree['phones'], currency='ZAR')
        listing(bob, title='Samsung Galaxy S21', price=50, category=tree['phones'], currency='ZAR', status='sold')
        # None of these may count:
        listing(bob, title='Samsung Galaxy S21', price=9000, category=tree['furniture'], currency='ZAR')
        listing(bob, title='Samsung Galaxy S21', price=9000, category=tree['phones'], currency='USD')
        listing(bob, title='Samsung Galaxy S21', price=9000, category=tree['phones'], currency='ZAR',
                moderation_status='removed')
        listing(mallory, title='Samsung Galaxy S21', price=9000, category=tree['phones'], currency='ZAR')
        listing(bob, title='Kettle', price=9000, category=tree['phones'], currency='ZAR')
        Block.objects.create(blocker=alice, blocked=mallory)
        with ai_draft():
            r = post_draft(alice, currency='zar')
        s = r.data['price_suggestion']
        assert s['based_on'] == 6 and s['currency'] == 'ZAR'
        prices = [50, 100, 200, 300, 400, 500]
        q1, median, q3 = pricing.quartiles(prices)
        assert (s['low'], s['median'], s['high']) == (round(q1, 2), round(median, 2), round(q3, 2))
        assert (s['low'], s['median'], s['high']) == (125.0, 250.0, 375.0)

    def test_too_few_comparables_gives_no_price(self, alice, bob, tree):
        for price in (100, 200, 300):
            listing(bob, title='Samsung Galaxy S21', price=price, category=tree['phones'], currency='ZAR')
        assert pricing.suggest(alice, 'Samsung Galaxy S21', tree['phones'], 'ZAR') is None
        listing(bob, title='Galaxy S21 Samsung', price=Decimal('250'), category=tree['phones'], currency='ZAR')
        assert pricing.suggest(alice, 'Samsung Galaxy S21', tree['phones'], 'ZAR')['median'] == 225.0

    def test_keywords_ignore_filler(self):
        assert pricing.keywords('The NEW Samsung phone, used, for sale!') == ['samsung', 'phone']
