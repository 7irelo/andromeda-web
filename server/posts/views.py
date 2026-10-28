import logging
from django.db.models import OuterRef, Prefetch, Q, Subquery
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.throttling import ScopedRateThrottle

from core import ai_client, visibility
from core.permissions import IsOwnerOrReadOnly
from . import feed
from .models import Post, Like, Comment, CommentLike, HiddenPost, PostRevision, SavedPost
from .serializers import (
    CommentSerializer, PostRevisionSerializer, PostSerializer,
    can_moderate_comments, viewer_state, visible_comments,
)
from moderation.tasks import queue_moderation
from .tasks import process_post, queue_new_post_event

logger = logging.getLogger(__name__)

VALID_REACTIONS = {choice for choice, _ in Like.REACTION_CHOICES}
COMPOSE_MAX_CHARS = 5000


class ComposeAssistSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=COMPOSE_MAX_CHARS, trim_whitespace=True)
    action = serializers.ChoiceField(choices=['friendlier', 'formal', 'shorter', 'grammar', 'translate'])
    language = serializers.ChoiceField(choices=['en', 'zu', 'af', 'st', 'xh'], required=False, allow_null=True)
    kind = serializers.ChoiceField(choices=['post', 'listing'], default='post')

    def validate(self, attrs):
        if attrs['action'] == 'translate' and not attrs.get('language'):
            raise serializers.ValidationError({'language': 'Choose a language to translate into.'})
        if attrs['action'] != 'translate':
            attrs['language'] = None
        return attrs


class PostViewSet(viewsets.ModelViewSet):
    serializer_class = PostSerializer
    permission_classes = [IsOwnerOrReadOnly]
    owner_field = 'author'
    throttle_scope = None  # set per action (compose_assist uses 'ai')
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']
    # Numeric ids only, so /posts/comments/ and /posts/saved/ never resolve as a post.
    lookup_value_regex = r'\d+'

    def _base_queryset(self):
        return visibility.visible_posts(self.request.user).select_related(
            'author', 'group', 'page',
            'shared_post__author', 'shared_post__group', 'shared_post__page',
        ).prefetch_related('media', 'tags', 'shared_post__media', 'shared_post__tags')

    def get_queryset(self):
        qs = self._base_queryset()

        author_id = self.request.query_params.get('author')
        if author_id and author_id.isdigit():
            qs = qs.filter(author_id=author_id)

        tag = self.request.query_params.get('tag', '').strip().lstrip('#').lower()[:50]
        if tag:
            qs = qs.filter(tags__name=tag)

        group_id = self.request.query_params.get('group')
        if group_id and group_id.isdigit():
            qs = qs.filter(group_id=group_id)

        # 'page' is taken by pagination, hence 'page_id'.
        page_id = self.request.query_params.get('page_id')
        if page_id and page_id.isdigit():
            qs = qs.filter(page_id=page_id)

        search = self.request.query_params.get('search', '').strip()[:200]
        if search:
            qs = qs.filter(
                Q(content__icontains=search) |
                Q(link_title__icontains=search) |
                Q(link_description__icontains=search) |
                Q(author__username__icontains=search) |
                Q(author__first_name__icontains=search) |
                Q(author__last_name__icontains=search) |
                Q(tags__name__icontains=search)
            ).distinct()

        return qs.order_by('-created_at')

    def _serialize(self, posts, reasons=None):
        posts = list(posts)
        context = {**self.get_serializer_context(), 'viewer_state': viewer_state(self.request.user, posts),
                   'reasons': reasons or {}}
        return PostSerializer(posts, many=True, context=context).data

    def list(self, request, *args, **kwargs):
        if request.query_params.get('feed') == 'true':
            return self._feed(request)
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response(self._serialize(page))

    def _feed(self, request):
        """Home feed: ranked (``sort=top``, default) or chronological (``sort=latest``), cursor-paginated."""
        sort = request.query_params.get('sort', feed.SORT_TOP)
        if sort not in (feed.SORT_TOP, feed.SORT_LATEST):
            raise ValidationError({'sort': 'Use "top" or "latest".'})
        posts, cursor, reasons = feed.feed_page(
            request.user, self._base_queryset(), sort, request.query_params.get('cursor', ''))
        next_url = None
        if cursor:
            next_url = request.build_absolute_uri(
                f'{request.path}?feed=true&sort={sort}&cursor={cursor}')
        return Response({
            'next': next_url, 'next_cursor': cursor, 'previous': None,
            'results': self._serialize(posts, reasons),
        })

    def perform_create(self, serializer):
        post = serializer.save(author=self.request.user)
        process_post(post, created=True)
        queue_new_post_event(post)

    def perform_update(self, serializer):
        post = serializer.instance
        previous = post.content
        changed = 'content' in serializer.validated_data and serializer.validated_data['content'] != previous
        media_changed = 'images' in serializer.validated_data or 'media_order' in serializer.validated_data
        if changed:
            PostRevision.objects.create(post=post, content=previous)
        post = serializer.save(is_edited=post.is_edited or changed or media_changed)
        process_post(post, created=False)

    @action(detail=True, methods=['post'])
    def react(self, request, pk=None):
        post = self.get_object()
        reaction = request.data.get('reaction', 'like')
        if reaction not in VALID_REACTIONS:
            raise ValidationError({'reaction': f'Choose one of: {", ".join(sorted(VALID_REACTIONS))}.'})
        like, created = Like.objects.get_or_create(
            user=request.user, post=post, defaults={'reaction': reaction}
        )
        if not created:
            if like.reaction == reaction:
                like.delete()
                return Response({'reacted': False})
            like.reaction = reaction
            like.save(update_fields=['reaction'])
        elif post.author_id != request.user.id:
            try:
                from notifications.tasks import send_like_notification
                send_like_notification.apply_async(
                    args=[request.user.id, post.author_id, post.id],
                    queue='notifications',
                )
            except Exception:
                logger.warning('Background dispatch failed', exc_info=True)
        return Response({'reacted': True, 'reaction': like.reaction})

    @action(detail=True, methods=['post'])
    def share(self, request, pk=None):
        original = self.get_object()
        # Re-sharing widens the audience, so only public posts (or your own) can be shared.
        if original.privacy != Post.PRIVACY_PUBLIC and original.author_id != request.user.id:
            raise PermissionDenied('Only public posts can be shared.')
        if original.group_id and original.group.privacy != 'public':
            raise PermissionDenied('Posts from private groups cannot be shared.')
        content = str(request.data.get('content', ''))[:10000]
        shared = Post.objects.create(
            author=request.user,
            content=content,
            post_type=Post.TYPE_TEXT,
            shared_post=original,
        )
        Post.objects.filter(pk=original.pk).update(
            shares_count=Post.objects.filter(shared_post=original).count()
        )
        process_post(shared, created=True)
        queue_new_post_event(shared)
        return Response(PostSerializer(shared, context={'request': request}).data, status=201)

    @action(detail=True, methods=['get', 'post'])
    def comments(self, request, pk=None):
        post = self.get_object()
        user = request.user
        if request.method == 'GET':
            replies = visible_comments(user, Comment.objects.select_related('author'))
            comments = list(
                visible_comments(user, post.comments.filter(parent=None)).select_related('author')
                .prefetch_related(Prefetch('replies', queryset=replies, to_attr='visible_replies'))[:200]
            )
            ids = [c.id for c in comments] + [r.id for c in comments for r in c.visible_replies]
            context = {
                'request': request,
                'liked_comments': set(CommentLike.objects.filter(user=user, comment_id__in=ids)
                                      .values_list('comment_id', flat=True)),
                'moderates_post': can_moderate_comments(user, post),
            }
            return Response(CommentSerializer(comments, many=True, context=context).data)
        serializer = CommentSerializer(data=request.data, context={'request': request, 'post': post})
        serializer.is_valid(raise_exception=True)
        comment = serializer.save(author=user, post=post)
        queue_moderation('comment', comment.id)
        if post.author_id != user.id:
            try:
                from notifications.tasks import send_comment_notification
                send_comment_notification.apply_async(
                    args=[user.id, post.author_id, post.id, comment.id],
                    queue='notifications',
                )
            except Exception:
                logger.warning('Background dispatch failed', exc_info=True)
        return Response(CommentSerializer(comment, context={'request': request}).data, status=201)

    @action(detail=True, methods=['get'])
    def revisions(self, request, pk=None):
        """Earlier versions of the post's text, newest first. Visible to anyone who can see the post."""
        post = self.get_object()
        return Response(PostRevisionSerializer(post.revisions.all()[:50], many=True).data)

    @action(detail=True, methods=['post', 'delete'], url_path='save')
    def bookmark(self, request, pk=None):
        post = self.get_object()
        if request.method == 'DELETE':
            SavedPost.objects.filter(user=request.user, post=post).delete()
            return Response({'saved': False})
        SavedPost.objects.get_or_create(user=request.user, post=post)
        return Response({'saved': True})

    @action(detail=True, methods=['post', 'delete'])
    def hide(self, request, pk=None):
        """Hide a post from your own feed. Nobody else is affected."""
        post = self.get_object()
        if request.method == 'DELETE':
            HiddenPost.objects.filter(user=request.user, post=post).delete()
            return Response({'hidden': False})
        HiddenPost.objects.get_or_create(user=request.user, post=post)
        return Response({'hidden': True})

    @action(detail=False, methods=['get'])
    def saved(self, request):
        """Your saved posts, most recently saved first. Posts you can no longer see drop out."""
        mine = SavedPost.objects.filter(user=request.user)
        qs = self._base_queryset().filter(id__in=mine.values('post_id')).annotate(
            saved_at=Subquery(mine.filter(post=OuterRef('pk')).values('created_at')[:1])
        ).order_by('-saved_at', '-id')
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(self._serialize(page))

    @action(detail=False, methods=['post'], url_path='compose-assist', permission_classes=[IsAuthenticated],
            throttle_classes=[*api_settings.DEFAULT_THROTTLE_CLASSES, ScopedRateThrottle], throttle_scope='ai')
    def compose_assist(self, request):
        """
        "Help me write": a rewritten draft (tone, grammar, shorter, or a
        translation) for a post or listing. Nothing is saved or replaced: the
        author accepts or discards the suggestion, and publishing still goes
        through moderation as usual.
        """
        if request.user.ai_opt_out:
            return Response({'detail': 'You have turned off AI features in your settings.'}, status=403)
        body = ComposeAssistSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            res = ai_client.call('/v1/compose', body.validated_data, user_id=request.user.id)
        except ai_client.AIRejected as exc:
            if exc.status == 429:
                return Response({'detail': "You've used today's AI allowance. Try again tomorrow."}, status=429)
            return Response({'detail': exc.detail}, status=exc.status)
        except ai_client.AIUnavailable:
            return Response({'detail': 'Writing help is not available right now.'}, status=503)
        return Response({'text': str(res.get('text', ''))[:COMPOSE_MAX_CHARS * 2],
                         'truncated': bool(res.get('truncated'))})


class CommentViewSet(mixins.RetrieveModelMixin, mixins.UpdateModelMixin, mixins.DestroyModelMixin,
                     viewsets.GenericViewSet):
    """
    A single comment. Anyone who can see it can read and like it; only its
    author can edit it; its author, the post's author, the page's admins and
    the group's admins and moderators can delete it.
    """

    serializer_class = CommentSerializer
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        user = self.request.user
        return visible_comments(user, Comment.objects.filter(
            post__in=visibility.visible_posts(user)
        )).select_related('post', 'post__group', 'post__page', 'author')

    def perform_update(self, serializer):
        if serializer.instance.author_id != self.request.user.id:
            raise PermissionDenied('You can only edit your own comments.')
        changed = serializer.validated_data.get('content', serializer.instance.content) != serializer.instance.content
        comment = serializer.save(is_edited=serializer.instance.is_edited or changed)
        if changed:
            queue_moderation('comment', comment.id)

    def perform_destroy(self, instance):
        user = self.request.user
        if instance.author_id != user.id and not can_moderate_comments(user, instance.post):
            raise PermissionDenied('You can only delete your own comments or comments on your posts.')
        instance.delete()

    @action(detail=True, methods=['post'])
    def like(self, request, pk=None):
        """Toggle your like on a comment."""
        comment = self.get_object()
        like, created = CommentLike.objects.get_or_create(user=request.user, comment=comment)
        if not created:
            like.delete()
        count = CommentLike.objects.filter(comment=comment).count()
        Comment.objects.filter(pk=comment.pk).update(likes_count=count)
        return Response({'liked': created, 'likes_count': count})
