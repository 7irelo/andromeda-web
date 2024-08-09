from django.shortcuts import get_object_or_404
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
        posts = Post.nodes.filter(content__icontains=query).order_by('-updated', '-created')
        serializer = PostSerializer(posts, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = PostSerializer(data=request.data)
        if serializer.is_valid():
            post = serializer.save(creator=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PostView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, uid):
        post = get_object_or_404(Post.nodes, uid=uid)
        comments = Comment.nodes.filter(post=post).order_by("created")
        post_serializer = PostSerializer(post)
        comments_serializer = CommentSerializer(comments, many=True)
        return Response({
            "post": post_serializer.data,
            "comments": comments_serializer.data
        })

    def post(self, request, uid):
        post = get_object_or_404(Post, uid=uid)
        serializer = CommentSerializer(data=request.data)
        if serializer.is_valid():
            comment = serializer.save(user=request.user, post=post)
            post.participants.connect(request.user)
            return Response({
                "post": PostSerializer(post).data,
                "comment": CommentSerializer(comment).data
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, uid):
        post = get_object_or_404(Post, uid=uid)
        serializer = PostSerializer(post, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, uid):
        post = get_object_or_404(Post, uid=uid)
        post.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class CommentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, post_uid, uid):
        comment = get_object_or_404(Comment.nodes, post__uid=post_uid, uid=uid)
        serializer = CommentSerializer(comment)
        return Response(serializer.data)

    def post(self, request, post_uid):
        post = get_object_or_404(Post.nodes, uid=post_uid)
        serializer = CommentSerializer(data=request.data)
        if serializer.is_valid():
            comment = serializer.save(user=request.user, post=post)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, post_uid, uid):
        comment = get_object_or_404(Comment.nodes, post__uid=post_uid, uid=uid)
        serializer = CommentSerializer(comment, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, post_uid, uid):
        comment = get_object_or_404(Comment.nodes, post__uid=post_uid, uid=uid)
        comment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
