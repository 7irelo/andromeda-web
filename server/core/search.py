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
        rank = SearchRank(SearchVector(*fields), SearchQuery(query, search_type='websearch'))
        partial = Q()
        for f in fields:
            partial |= Q(**{f'{f}__icontains': query})
        # Ranked full-text matches first; substring matches keep prefix search working.
        return qs.annotate(_rank=rank).filter(Q(_rank__gt=0) | partial).order_by('-_rank')
    cond = Q()
    for f in fields:
        cond |= Q(**{f'{f}__icontains': query})
    return qs.filter(cond)


def _people(user, q):
    User = get_user_model()
    qs = User.objects.filter(is_active=True, searchable=True).exclude(id__in=visibility.blocked_ids(user))
    return _text_filter(qs, ['username', 'first_name', 'last_name'], q)


def _posts(user, q):
    return _text_filter(visibility.visible_posts(user).select_related('author'), ['content', 'link_title'], q)


def _groups(user, q):
    return _text_filter(visibility.visible_groups(user), ['name', 'description'], q)


def _pages(user, q):
    from pages.models import Page
    return _text_filter(Page.objects.all(), ['name', 'description'], q)


def _listings(user, q):
    from marketplace.models import Listing
    qs = Listing.objects.filter(status=Listing.STATUS_ACTIVE).exclude(moderation_status='removed').exclude(
        seller_id__in=visibility.blocked_ids(user)).prefetch_related('images')
    return _text_filter(qs, ['title', 'description'], q)


def _videos(user, q):
    from watch.models import Video
    qs = Video.objects.filter(status=Video.STATUS_READY, is_public=True).exclude(
        uploader_id__in=visibility.blocked_ids(user)).select_related('uploader')
    return _text_filter(qs, ['title', 'description'], q)


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
            results[name] = serializer(rows, many=True, context=ctx).data
        return Response({'query': q, 'results': results})
