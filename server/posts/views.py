from django.shortcuts import get_object_or_404
from django.db.models import Q
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from .models import Post, Comment
from .serializers import PostSerializer, CommentSerializer

class PostsView(APIView):
    def get(self, request):
        query = request.GET.get("q", "")
        posts = Post.objects.filter(Q(host__username__icontains=query) | Q(text__icontains=query))
        serializer = PostSerializer(posts, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class PostView(APIView):
    def get(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        comments = Comment.objects.filter(post=post).order_by("created")
        post_serializer = PostSerializer(post)
        comments_serializer = CommentSerializer(comments, many=True)
        return Response({
            "post": post_serializer.data,
            "comments": comments_serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        comment = Comment.objects.create(
            user=request.user,
            post=post,
            text=request.data.get("text")
        )
        post.participants.add(request.user)
        post_serializer = PostSerializer(post)
        comment_serializer = CommentSerializer(comment)
        return Response({
            "post": post_serializer.data,
            "comment": comment_serializer.data
        }, status=status.HTTP_201_CREATED)

class CreatePostView(APIView):
    def post(self, request):
        serializer = PostSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(host=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UpdatePostView(APIView):
    def put(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        serializer = PostSerializer(post, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class DeletePostView(APIView):
    def delete(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        post.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class DeleteCommentView(APIView):
    def delete(self, request, pk):
        comment = get_object_or_404(Comment, pk=pk)
        comment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
