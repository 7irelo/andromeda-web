from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from .models import Post, Comment
from .serializers import PostSerializer, CommentSerializer

class PostView(APIView):
    def get(self, request, pk):
        post = get_object_or_404(Post, id=pk)
        comments = post.comment_set.all().order_by("created")
        participants = post.participants.all()
        serializer = PostSerializer(post)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, pk):
        post = get_object_or_404(Post, id=pk)
        Comment.objects.create(
            user=request.user,
            post=post,
            text=request.data.get("text")
        )
        post.participants.add(request.user)
        serializer = PostSerializer(post)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
class CreatePostView(APIView):
    def post(self, request):
        post_text = request.data.get("text")
        post = Post.objects.create(host=request.user, text=post_text)
        serializer = PostSerializer(post)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class UpdatePostView(APIView):
    def put(self, request, pk):
        post = get_object_or_404(Post, id=pk)
        post.text = request.data.get("text")
        post.save()
        serializer = PostSerializer(post)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
class DeletePostView(APIView):
    def delete(self, request, pk):
        post = get_object_or_404(Post, id=pk)
        post.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class DeleteCommentView(APIView):
    def delete(self, request, pk):
        comment = get_object_or_404(Comment, id=pk)
        comment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
