"""
Global search across people, posts, groups, pages, listings and videos.

Every result set is built from the same visibility-filtered querysets the
feature endpoints use, so search can never surface something the viewer
couldn't open directly.
"""
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import Q
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core import visibility

MAX_QUERY = 100
PER_TYPE_PREVIEW = 5
PER_TYPE_FULL = 30


def _text_filter(qs, fields, query):
    """Postgres full-text search when available, case-insensitive substring otherwise."""
    if connection.vendor == 'postgresql':
        from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
        vector, sq = SearchVector(*fields), SearchQuery(query, search_type='websearch')
        partial = Q()
        for f in fields:
            partial |= Q(**{f'{f}__icontains': query})
        # Filter on an actual match (ts_rank is never exactly 0, so it can't be the filter).
        # Ranked full-text matches first; substring matches keep prefix search working.
        return qs.annotate(_sv=vector, _rank=SearchRank(vector, sq)).filter(Q(_sv=sq) | partial).order_by('-_rank')
    cond = Q()
    for f in fields:
        cond |= Q(**{f'{f}__icontains': query})
    return qs.filter(cond)


def visible_listings(user):
    from marketplace.models import Listing
    from marketplace.views import _with_ratings
    qs = Listing.objects.filter(status__in=Listing.PUBLIC_STATUSES).exclude(moderation_status='removed').exclude(
        seller_id__in=visibility.blocked_ids(user)).select_related('seller', 'category').prefetch_related('images')
    # Ratings and the viewer's saved flag as subqueries, as on the listings endpoint.
    return _with_ratings(qs, user) if user.is_authenticated else qs


def visible_pages(user):
    from pages.models import Page
    return Page.objects.select_related('created_by')


def visible_videos(user):
    from watch.models import Video
    return Video.objects.filter(status=Video.STATUS_READY, is_public=True).exclude(moderation_status='removed').exclude(
        uploader_id__in=visibility.blocked_ids(user)).select_related('uploader')


# What each searchable content type exposes to a viewer, and which text fields
# lexical search matches. Semantic search reuses the same querysets.
CONTENT = {
    'posts': (lambda u: visibility.visible_posts(u).select_related('author', 'group', 'page', 'shared_post__author')
              .prefetch_related('media', 'tags'), ['content', 'link_title']),
    'groups': (lambda u: visibility.visible_groups(u).select_related('created_by'), ['name', 'description']),
    'pages': (visible_pages, ['name', 'description']),
    'listings': (visible_listings, ['title', 'description']),
    'videos': (visible_videos, ['title', 'description']),
}


def lexical(kind, user, q):
    finder, fields = CONTENT[kind]
    return _text_filter(finder(user), fields, q)


def _people(user, q):
    User = get_user_model()
    qs = User.objects.filter(is_active=True, searchable=True).exclude(id__in=visibility.blocked_ids(user))
    return _text_filter(qs, ['username', 'first_name', 'last_name'], q)


def _posts(user, q):
    return lexical('posts', user, q)


def _groups(user, q):
    return lexical('groups', user, q)


def _pages(user, q):
    return lexical('pages', user, q)


def _listings(user, q):
    return lexical('listings', user, q)


def _videos(user, q):
    return lexical('videos', user, q)


def _serializers():
    from groups.serializers import GroupSerializer
    from marketplace.serializers import ListingSerializer
    from pages.serializers import PageSerializer
    from posts.serializers import PostSerializer
    from users.serializers import UserSerializer
    from watch.serializers import VideoSerializer
    return {
        'people': (_people, UserSerializer),
        'posts': (_posts, PostSerializer),
        'groups': (_groups, GroupSerializer),
        'pages': (_pages, PageSerializer),
        'listings': (_listings, ListingSerializer),
        'videos': (_videos, VideoSerializer),
    }


class SearchQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=MAX_QUERY, trim_whitespace=True)
    type = serializers.ChoiceField(
        choices=['all', 'people', 'posts', 'groups', 'pages', 'listings', 'videos'], default='all'
    )


class SearchView(APIView):
    def get(self, request):
        params = SearchQuerySerializer(data=request.query_params)
        if not params.is_valid():
            raise ValidationError(params.errors)
        q, kind = params.validated_data['q'], params.validated_data['type']
        if len(q) < 2:
            raise ValidationError({'q': 'Type at least 2 characters.'})
        registry = _serializers()
        types = registry if kind == 'all' else {kind: registry[kind]}
        limit = PER_TYPE_PREVIEW if kind == 'all' else PER_TYPE_FULL
        ctx = {'request': request}
        results = {}
        for name, (finder, serializer) in types.items():
            rows = list(finder(request.user, q).distinct()[:limit])
            context = ctx
            if name == 'posts':
                from posts.serializers import viewer_state
                context = {**ctx, 'viewer_state': viewer_state(request.user, rows)}
            results[name] = serializer(rows, many=True, context=context).data
        return Response({'query': q, 'results': results})
