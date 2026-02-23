from django.db.models import Q
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from users.models import FriendRequest
from .models import Post, Like, Comment
from .serializers import PostSerializer, CommentSerializer


class PostViewSet(viewsets.ModelViewSet):
    serializer_class = PostSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Post.objects.select_related('author', 'shared_post__author').prefetch_related(
            'media', 'tags'
        )

        # Feed: posts from friends + own posts
        feed_filter = self.request.query_params.get('feed')
        if feed_filter == 'true':
            accepted = FriendRequest.objects.filter(
                status=FriendRequest.STATUS_ACCEPTED
            ).filter(Q(sender=user) | Q(receiver=user))
            friend_ids = set()
            for fr in accepted:
                friend_ids.add(fr.sender_id if fr.receiver_id == user.id else fr.receiver_id)
            qs = qs.filter(
                Q(author_id__in=friend_ids) | Q(author=user),
                privacy__in=['public', 'friends'],
            )

        author_id = self.request.query_params.get('author')
        if author_id:
            qs = qs.filter(author_id=author_id)

        group_id = self.request.query_params.get('group')
        if group_id:
            qs = qs.filter(group_id=group_id)

        search = self.request.query_params.get('search')
        if search:
            search = search.strip()
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
        serializer.save(author=self.request.user)

    def perform_update(self, serializer):
        serializer.save(is_edited=True)

    @action(detail=True, methods=['post'])
    def react(self, request, pk=None):
        post = self.get_object()
        reaction = request.data.get('reaction', 'like')
        like, created = Like.objects.get_or_create(user=request.user, post=post)
        if not created:
            if like.reaction == reaction:
                # Toggle off
                like.delete()
                return Response({'reacted': False})
            like.reaction = reaction
            like.save()
        else:
            like.reaction = reaction
            like.save()
            # Trigger notification via Celery
            try:
                from notifications.tasks import send_like_notification
                send_like_notification.apply_async(
                    args=[request.user.id, post.author_id, post.id],
                    queue='notifications',
                )
            except Exception:
                pass
        return Response({'reacted': True, 'reaction': like.reaction})

    @action(detail=True, methods=['post'])
    def share(self, request, pk=None):
        original = self.get_object()
        shared = Post.objects.create(
            author=request.user,
            content=request.data.get('content', ''),
            post_type=Post.TYPE_TEXT,
            shared_post=original,
        )
        Post.objects.filter(pk=original.pk).update(shares_count=Post.objects.filter(shared_post=original).count())
        return Response(PostSerializer(shared, context={'request': request}).data, status=201)

    @action(detail=True, methods=['get', 'post'])
    def comments(self, request, pk=None):
        post = self.get_object()
        if request.method == 'GET':
            comments = post.comments.filter(parent=None).select_related('author').prefetch_related('replies__author')
            return Response(CommentSerializer(comments, many=True, context={'request': request}).data)
        serializer = CommentSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        comment = serializer.save(author=request.user, post=post)
        # Trigger notification
        try:
            from notifications.tasks import send_comment_notification
            send_comment_notification.apply_async(
                args=[request.user.id, post.author_id, post.id, comment.id],
                queue='notifications',
            )
        except Exception:
            pass
        return Response(CommentSerializer(comment, context={'request': request}).data, status=201)


class CommentViewSet(viewsets.ModelViewSet):
    serializer_class = CommentSerializer

    def get_queryset(self):
        return Comment.objects.filter(author=self.request.user)

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    def perform_update(self, serializer):
        serializer.save()
