from django.shortcuts import get_object_or_404
from django.db.models import Q
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .models import Post, Comment
from .serializers import PostSerializer, CommentSerializer
from .recommendations import get_recommended_posts


class RecommendedPostsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        recommended_posts = get_recommended_posts(user)
        serializer = PostSerializer(recommended_posts, many=True)
        return Response(serializer.data)

class PostsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = request.GET.get("q", "")
        posts = Post.objects.filter(
            Q(host__username__icontains(query) | Q(text__icontains(query))
        ).select_related('host').prefetch_related('participants').all()
        serializer = PostSerializer(posts, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = PostSerializer(data=request.data)
        if serializer.is_valid():
            post = serializer.save(host=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PostView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        post = get_object_or_404(Post.objects.select_related('host').prefetch_related('participants'), pk=pk)
        comments = Comment.objects.filter(post=post).select_related('user').order_by("created").all()
        post_serializer = PostSerializer(post)
        comments_serializer = CommentSerializer(comments, many=True)
        return Response({
            "post": post_serializer.data,
            "comments": comments_serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        serializer = CommentSerializer(data=request.data)
        if serializer.is_valid():
            comment = Comment.objects.create(
                user=request.user,
                post=post,
                text=serializer.validated_data['text']
            )
            post.participants.add(request.user)
            comment_serializer = CommentSerializer(comment)
            return Response({
                "post": PostSerializer(post).data,
                "comment": comment_serializer.data
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        serializer = PostSerializer(post, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        post.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CommentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, post_pk, pk):
        comment = get_object_or_404(Comment.objects.select_related('user', 'post'), post_id=post_pk, pk=pk)
        serializer = CommentSerializer(comment)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, post_pk):
        post = get_object_or_404(Post, pk=post_pk)
        serializer = CommentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user, post=post)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, post_pk, pk):
        comment = get_object_or_404(Comment, post_id=post_pk, pk=pk)
        serializer = CommentSerializer(comment, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, post_pk, pk):
        comment = get_object_or_404(Comment, post_id=post_pk, pk=pk)
        comment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
