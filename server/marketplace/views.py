import base64
import io
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Avg, Count, Exists, F, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from PIL import Image
from rest_framework import viewsets, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from core import ai_client, visibility
from core.search import _text_filter
from moderation.tasks import queue_moderation
from core.permissions import IsOwnerOrReadOnly
from core.validators import sanitize_image
from . import geo, pricing
from .models import Listing, ListingImage, ListingLike, Category, Review
from .serializers import (CategoryTreeSerializer, DraftRequestSerializer, ListingImageSerializer, ListingSerializer,
                          ReviewSerializer, seller_rating)
from .tasks import notify_price_drop


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """The category tree: top-level categories with their children nested."""

    queryset = Category.objects.filter(parent=None).prefetch_related('children').order_by('name')
    serializer_class = CategoryTreeSerializer
    pagination_class = None


MAX_IMAGES_PER_LISTING = 10
MAX_DRAFT_IMAGES = 4
DRAFT_IMAGE_EDGE = 1568        # longest edge sent to the model; larger only costs tokens
MAX_SEARCH = 100
SORTS = {'newest': ('-created_at',), 'price_asc': ('price', '-created_at'), 'price_desc': ('-price', '-created_at')}


def _clean_images(files, existing=0, limit=MAX_IMAGES_PER_LISTING):
    if existing + len(files) > limit:
        raise ValidationError({'images': f'A listing can have at most {limit} images.'})
    try:
        return [sanitize_image(f) for f in files]
    except DjangoValidationError as exc:
        raise ValidationError({'images': exc.messages})


def _decimal(params, name):
    raw = params.get(name)
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        raise ValidationError({name: 'Must be a number.'})
    if not value.is_finite() or value < 0:
        raise ValidationError({name: 'Must be a positive number.'})
    return value


def _float(params, name):
    raw = params.get(name)
    if raw in (None, ''):
        return None
    try:
        return float(raw)
    except ValueError:
        raise ValidationError({name: 'Must be a number.'})


def _category_ids(slug):
    """A category and all its descendants. The tree is small, so it's walked in Python."""
    rows = list(Category.objects.values_list('id', 'slug', 'parent_id'))
    root = next((pk for pk, s, _ in rows if s == slug), None)
    if root is None:
        return []
    ids, frontier = {root}, {root}
    while frontier:
        frontier = {pk for pk, _, parent in rows if parent in frontier and pk not in ids}
        ids |= frontier
    return list(ids)


def _with_ratings(qs, user):
    """Rating aggregates and the viewer's saved flag as subqueries, so a page of listings is one query."""
    listing_reviews = Review.objects.filter(listing=OuterRef('pk')).order_by().values('listing')
    seller_reviews = Review.objects.filter(listing__seller=OuterRef('seller')).order_by().values('listing__seller')
    return qs.annotate(
        rating_avg=Subquery(listing_reviews.annotate(a=Avg('rating')).values('a')),
        rating_count=Coalesce(Subquery(listing_reviews.annotate(c=Count('id')).values('c')),
                              Value(0), output_field=IntegerField()),
        seller_rating_avg=Subquery(seller_reviews.annotate(a=Avg('rating')).values('a')),
        seller_rating_count=Coalesce(Subquery(seller_reviews.annotate(c=Count('id')).values('c')),
                                     Value(0), output_field=IntegerField()),
        is_liked_annotated=Exists(ListingLike.objects.filter(listing=OuterRef('pk'), user=user)),
    )


def _viewer_point(params):
    lat, lng = _float(params, 'lat'), _float(params, 'lng')
    city = params.get('city')
    if lat is None and lng is None and city:
        point = geo.centroid_for(city)
        if point is None:
            raise ValidationError({'city': 'Unknown city.'})
        return point
    if lat is None and lng is None:
        return None
    if not geo.valid_point(lat, lng):
        raise ValidationError({'lat': 'Send a valid lat and lng together.'})
    return lat, lng


class ListingViewSet(viewsets.ModelViewSet):
    serializer_class = ListingSerializer
    permission_classes = [IsOwnerOrReadOnly]
    owner_field = 'seller'
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']
    # Filtering, search and sorting are handled explicitly in get_queryset().
    filter_backends = []
    # Only the actions that add ScopedRateThrottle set a scope (see draft()).
    throttle_scope = None

    def _visible(self):
        """What the viewer may open: public listings from people they haven't blocked, plus their own."""
        user = self.request.user
        return Listing.objects.filter(
            (Q(status__in=Listing.PUBLIC_STATUSES) & ~Q(moderation_status='removed')) | Q(seller=user)
        ).exclude(seller_id__in=visibility.blocked_ids(user))

    def get_queryset(self):
        params = self.request.query_params
        user = self.request.user
        if self.action != 'list':
            qs = self._visible()
        elif params.get('mine') == 'true':
            qs = Listing.objects.filter(seller=user)
            wanted = params.get('status')
            if wanted:
                if wanted not in dict(Listing.STATUS_CHOICES):
                    raise ValidationError({'status': 'Unknown status.'})
                qs = qs.filter(status=wanted)
        else:
            qs = self._visible().filter(status__in=Listing.PUBLIC_STATUSES).exclude(moderation_status='removed')
            qs = self._filter(qs, params)
        return _with_ratings(qs.select_related('seller', 'category'), user).prefetch_related('images')

    def _filter(self, qs, params):
        category = params.get('category')
        if category:
            qs = qs.filter(category_id__in=_category_ids(category))
        conditions = [c for c in params.get('condition', '').split(',') if c]
        if conditions:
            if not set(conditions) <= {c for c, _ in Listing.CONDITION_CHOICES}:
                raise ValidationError({'condition': 'Unknown condition.'})
            qs = qs.filter(condition__in=conditions)
        min_price, max_price = _decimal(params, 'min_price'), _decimal(params, 'max_price')
        if min_price is not None:
            qs = qs.filter(price__gte=min_price)
        if max_price is not None:
            qs = qs.filter(price__lte=max_price)

        sort = params.get('sort') or ''
        if sort and sort not in (*SORTS, 'nearest'):
            raise ValidationError({'sort': 'Unknown sort.'})
        point = _viewer_point(params)
        radius = _float(params, 'radius_km')
        if radius is not None and not 0 < radius <= geo.MAX_RADIUS_KM:
            raise ValidationError({'radius_km': f'Radius must be between 1 and {geo.MAX_RADIUS_KM} km.'})
        if (radius is not None or sort == 'nearest') and point is None:
            raise ValidationError({'lat': 'Distance filters need a location (lat and lng, or a city).'})
        if point is not None:
            qs = qs.annotate(distance=geo.distance_expression(*point))
            if radius is not None:
                min_lat, max_lat, min_lng, max_lng = geo.bounding_box(*point, radius)
                qs = qs.filter(latitude__range=(min_lat, max_lat), longitude__range=(min_lng, max_lng),
                               distance__lte=radius)

        search = (params.get('search') or '').strip()[:MAX_SEARCH]
        if search:
            # Full-text on Postgres (ranked), substring on SQLite. Explicit sorts override the ranking.
            qs = _text_filter(qs, ['title', 'description'], search)
        if sort == 'nearest':
            return qs.order_by(F('distance').asc(nulls_last=True), '-created_at')
        if sort:
            return qs.order_by(*SORTS[sort])
        return qs if search else qs.order_by('-created_at')

    def perform_create(self, serializer):
        images = _clean_images(self.request.FILES.getlist('images'))
        listing = serializer.save(seller=self.request.user)
        queue_moderation('listing', listing.id)
        for i, img in enumerate(images):
            ListingImage.objects.create(listing=listing, image=img, is_primary=(i == 0), order=i)

    def perform_update(self, serializer):
        old = serializer.instance
        old_price, old_text = old.price, (old.title, old.description)
        listing = serializer.save()
        if (listing.title, listing.description) != old_text:
            queue_moderation('listing', listing.id)
        if listing.price < old_price:
            transaction.on_commit(lambda: notify_price_drop.delay(listing.id, str(old_price)))

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.seller_id != request.user.id:
            Listing.objects.filter(pk=instance.pk).update(views_count=F('views_count') + 1)
        return super().retrieve(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def like(self, request, pk=None):
        """Save or unsave a listing (the bookmark heart)."""
        listing = self.get_object()
        if listing.seller_id == request.user.id:
            raise ValidationError({'detail': 'You cannot save your own listing.'})
        like, created = ListingLike.objects.get_or_create(user=request.user, listing=listing)
        if not created:
            like.delete()
        Listing.objects.filter(pk=listing.pk).update(likes_count=listing.liked_by.count())
        return Response({'liked': created})

    @action(detail=False, methods=['get'])
    def saved(self, request):
        """The viewer's saved listings that are still visible to them, most recently saved first."""
        saved_at = ListingLike.objects.filter(user=request.user, listing=OuterRef('pk')).values('created_at')
        qs = self._visible().filter(liked_by__user=request.user, status__in=Listing.PUBLIC_STATUSES).exclude(
            moderation_status='removed').annotate(saved_at=Subquery(saved_at)).order_by('-saved_at')
        qs = _with_ratings(qs.select_related('seller', 'category'), request.user).prefetch_related('images')
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @action(detail=False, methods=['get'], url_path='mine/counts')
    def mine_counts(self, request):
        rows = Listing.objects.filter(seller=request.user).values('status').annotate(n=Count('id'))
        counts = {s: 0 for s, _ in Listing.STATUS_CHOICES}
        counts.update({r['status']: r['n'] for r in rows})
        return Response({**counts, 'all': sum(counts.values())})

    @action(detail=True, methods=['post'])
    def upload_images(self, request, pk=None):
        listing = self.get_object()
        if listing.seller != request.user:
            return Response({'detail': 'Not allowed.'}, status=status.HTTP_403_FORBIDDEN)
        current_count = listing.images.count()
        images = _clean_images(request.FILES.getlist('images'), current_count)
        if not images:
            return Response({'detail': 'No images provided.'}, status=status.HTTP_400_BAD_REQUEST)
        created = []
        for i, img in enumerate(images):
            obj = ListingImage.objects.create(
                listing=listing, image=img, order=current_count + i, is_primary=current_count + i == 0
            )
            created.append(obj)
        return Response(
            ListingImageSerializer(created, many=True).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['get', 'post'])
    def reviews(self, request, pk=None):
        listing = self.get_object()
        if request.method == 'GET':
            reviews = listing.reviews.exclude(reviewer_id__in=visibility.blocked_ids(request.user))
            return Response(ReviewSerializer(
                reviews.select_related('reviewer'), many=True, context={'request': request}
            ).data)
        if listing.seller_id == request.user.id:
            raise PermissionDenied('You cannot review your own listing.')
        if listing.reviews.filter(reviewer=request.user).exists():
            raise ValidationError({'detail': 'You already reviewed this listing.'})
        serializer = ReviewSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save(reviewer=request.user, listing=listing)
        return Response(serializer.data, status=201)

    @action(detail=False, methods=['post'], url_path='draft',
            throttle_classes=[*api_settings.DEFAULT_THROTTLE_CLASSES, ScopedRateThrottle], throttle_scope='ai')
    def draft(self, request):
        """
        Listing Assistant: photos in, an editable draft out.

        The AI service suggests the title, description, category and condition;
        the price range comes from comparable listings here, never from the model.
        Nothing is saved: the seller edits the draft and creates the listing as
        usual, which sends it through moderation.
        """
        body = DraftRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        files = request.FILES.getlist('images')
        if not files:
            raise ValidationError({'images': 'Add at least one photo.'})
        images = [_for_model(img) for img in _clean_images(files, limit=MAX_DRAFT_IMAGES)]
        if not ai_client.enabled():
            return Response({'detail': 'The listing assistant is not available right now.'}, status=503)
        categories = list(Category.objects.select_related('parent').order_by('name'))
        payload = {
            'images': images,
            'hint': body.validated_data.get('hint', ''),
            'categories': [{'slug': c.slug, 'name': f'{c.parent.name} > {c.name}' if c.parent_id else c.name}
                           for c in categories],
        }
        try:
            res = ai_client.call('/v1/listing/draft', payload, user_id=request.user.id)
        except ai_client.AIRejected as exc:
            if exc.status == 429:
                return Response({'detail': "You've used today's AI allowance. Try again tomorrow."}, status=429)
            return Response({'detail': exc.detail}, status=exc.status)
        except ai_client.AIUnavailable:
            return Response({'detail': 'The listing assistant is not available right now.'}, status=503)

        draft = res['draft']
        by_slug = {c.slug: c for c in categories}
        category = by_slug.get(draft.get('category') or '')
        condition = draft.get('condition') if draft.get('condition') in dict(Listing.CONDITION_CHOICES) else None
        currency = body.validated_data['currency']
        return Response({
            'title': (draft.get('title') or '')[:255],
            'description': draft.get('description') or '',
            'category': {'id': category.id, 'slug': category.slug, 'name': category.name} if category else None,
            'condition': condition,
            'price_suggestion': pricing.suggest(request.user, draft.get('title') or '', category, currency),
            'ai_suggested': True,
        })


def _for_model(upload):
    """A sanitised image, downscaled and re-encoded as JPEG for the model."""
    upload.seek(0)
    img = Image.open(upload)
    img.thumbnail((DRAFT_IMAGE_EDGE, DRAFT_IMAGE_EDGE))
    if img.mode != 'RGB':
        img = img.convert('RGB')
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=85)
    return {'media_type': 'image/jpeg', 'data': base64.b64encode(buf.getvalue()).decode()}


class SellerView(APIView):
    """A seller's rating and their most recent reviews, hidden across blocks like everything else."""

    def get(self, request, pk):
        seller = get_object_or_404(get_user_model(), pk=pk, is_active=True)
        blocked = visibility.blocked_ids(request.user)
        if seller.id in blocked:
            return Response({'detail': 'Not found.'}, status=404)
        reviews = Review.objects.filter(listing__seller=seller).exclude(reviewer_id__in=blocked).select_related(
            'reviewer')[:20]
        return Response({
            'seller_id': seller.id,
            'rating': seller_rating(seller.id),
            'active_listings': Listing.objects.filter(seller=seller, status__in=Listing.PUBLIC_STATUSES).exclude(
                moderation_status='removed').count(),
            'reviews': ReviewSerializer(reviews, many=True, context={'request': request}).data,
        })


class CitiesView(APIView):
    """The built-in city list used for location filters and approximate positions."""

    def get(self, request):
        return Response([{'name': name, 'latitude': lat, 'longitude': lng}
                         for name, (lat, lng) in sorted(geo.CITY_CENTROIDS.items())])
