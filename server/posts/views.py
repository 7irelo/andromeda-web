from django.shortcuts import get_object_or_404
from django.db.models import Q
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from .models import Post, Comment
from .serializers import PostSerializer, CommentSerializer

class PostsView(APIView):
    async def get(self, request):
        query = request.GET.get("q", "")
        posts = await Post.objects.filter(Q(host__username__icontains=query) | Q(text__icontains(query))).all()
        serializer = PostSerializer(posts, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class PostView(APIView):
    async def get(self, request, pk):
        post = await get_object_or_404(Post, pk=pk)
        comments = await Comment.objects.filter(post=post).order_by("created").all()
        post_serializer = PostSerializer(post)
        comments_serializer = CommentSerializer(comments, many=True)
        return Response({
            "post": post_serializer.data,
            "comments": comments_serializer.data
        }, status=status.HTTP_200_OK)

    async def post(self, request, pk):
        post = await get_object_or_404(Post, pk=pk)
        comment = await Comment.objects.create(
            user=request.user,
            post=post,
            text=request.data.get("text")
        )
        await post.participants.add(request.user)
        post_serializer = PostSerializer(post)
        comment_serializer = CommentSerializer(comment)
        return Response({
            "post": post_serializer.data,
            "comment": comment_serializer.data
        }, status=status.HTTP_201_CREATED)

class CreatePostView(APIView):
    async def post(self, request):
        serializer = PostSerializer(data=request.data)
        if serializer.is_valid():
            await serializer.save(host=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UpdatePostView(APIView):
    async def put(self, request, pk):
        post = await get_object_or_404(Post, pk=pk)
        serializer = PostSerializer(post, data=request.data, partial=True)
        if serializer.is_valid():
            await serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class DeletePostView(APIView):
    async def delete(self, request, pk):
        post = await get_object_or_404(Post, pk=pk)
        await post.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class CommentView(APIView):
    async def get(self, request, post_pk, pk):
        comment = await get_object_or_404(Comment, post_id=post_pk, pk=pk)
        serializer = CommentSerializer(comment)
        return Response(serializer.data, status=status.HTTP_200_OK)

    async def post(self, request, post_pk):
        post = await get_object_or_404(Post, pk=post_pk)
        serializer = CommentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user, post=post)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    async def put(self, request, post_pk, pk):
        comment = await get_object_or_404(Comment, post_id=post_pk, pk=pk)
        serializer = CommentSerializer(comment, data=request.data, partial=True)
        if serializer.is_valid():
            await serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    async def delete(self, request, post_pk, pk):
        comment = await get_object_or_404(Comment, post_id=post_pk, pk=pk)
        await comment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
