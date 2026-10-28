import logging
from django.db.models import Q
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from core import visibility
from core.permissions import IsOwnerOrReadOnly
from .models import Post, Like, Comment
from .serializers import PostSerializer, CommentSerializer
from moderation.tasks import queue_moderation
from .tasks import process_post

logger = logging.getLogger(__name__)

VALID_REACTIONS = {choice for choice, _ in Like.REACTION_CHOICES}


class PostViewSet(viewsets.ModelViewSet):
    serializer_class = PostSerializer
    permission_classes = [IsOwnerOrReadOnly]
    owner_field = 'author'
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        user = self.request.user
        qs = visibility.visible_posts(user).select_related(
            'author', 'shared_post__author', 'group'
        ).prefetch_related('media', 'tags')

        if self.request.query_params.get('feed') == 'true':
            qs = qs.filter(Q(author_id__in=visibility.friend_ids(user)) | Q(author=user))

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

    def perform_create(self, serializer):
        process_post(serializer.save(author=self.request.user), created=True)

    def perform_update(self, serializer):
        process_post(serializer.save(is_edited=True), created=False)

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
        return Response(PostSerializer(shared, context={'request': request}).data, status=201)

    @action(detail=True, methods=['get', 'post'])
    def comments(self, request, pk=None):
        post = self.get_object()
        if request.method == 'GET':
            comments = post.comments.filter(parent=None).exclude(
                author_id__in=visibility.blocked_ids(request.user)
            ).exclude(Q(moderation_status='removed') & ~Q(author=request.user)).select_related('author').prefetch_related('replies__author')[:200]
            return Response(CommentSerializer(comments, many=True, context={'request': request}).data)
        serializer = CommentSerializer(data=request.data, context={'request': request, 'post': post})
        serializer.is_valid(raise_exception=True)
        comment = serializer.save(author=request.user, post=post)
        queue_moderation('comment', comment.id)
        if post.author_id != request.user.id:
            try:
                from notifications.tasks import send_comment_notification
                send_comment_notification.apply_async(
                    args=[request.user.id, post.author_id, post.id, comment.id],
                    queue='notifications',
                )
            except Exception:
                logger.warning('Background dispatch failed', exc_info=True)
        return Response(CommentSerializer(comment, context={'request': request}).data, status=201)


class CommentViewSet(viewsets.ModelViewSet):
    """Edit or delete a comment. Authors can edit; authors and the post's author can delete."""

    serializer_class = CommentSerializer
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        user = self.request.user
        return Comment.objects.filter(
            post__in=visibility.visible_posts(user)
        ).filter(Q(author=user) | Q(post__author=user)).select_related('post')

    def perform_update(self, serializer):
        if serializer.instance.author_id != self.request.user.id:
            raise PermissionDenied('You can only edit your own comments.')
        serializer.save()
