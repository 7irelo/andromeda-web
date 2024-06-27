from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.db.models import Q
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Post, Comment, User
from .forms import PostForm, UserForm, MyUserCreationForm
from .serializers import UserSerializer, PostSerializer, CommentSerializer
import jwt, datetime

class PostView(APIView):
    def get(self, request, pk):
        post = get_object_or_404(Post, id=pk)
        comments = post.comment_set.all().order_by("created")
        participants = post.participants.all()
        serializer = PostSerializer(post)
        return Response(serializer.data)

    def post(self, request, pk):
        post = get_object_or_404(Post, id=pk)
        Comment.objects.create(
            user=request.user,
            post=post,
            text=request.data.get("text")
        )
        post.participants.add(request.user)
        return redirect("post", pk=post.id)

class CreatePostView(APIView):
    def get(self, request):
        form = PostForm()
        return render(request, "posts/create_post.html", {"form": form})

    def post(self, request):
        post_text = request.data.get("text")
        Post.objects.create(host=request.user, text=post_text)
        return redirect("home")

class UpdatePostView(APIView):
    def get(self, request, pk):
        post = get_object_or_404(Post, id=pk)
        form = PostForm(instance=post)
        return render(request, "posts/update_post.html", {"form": form, "post": post})

    def post(self, request, pk):
        post = get_object_or_404(Post, id=pk)
        post.text = request.data.get("text")
        post.save()
        return redirect("home")

class DeletePostView(APIView):
    def get(self, request, pk):
        post = get_object_or_404(Post, id=pk)
        return render(request, "posts/delete_post.html", {"post": post})

    def post(self, request, pk):
        post = get_object_or_404(Post, id=pk)
        post.delete()
        return redirect("home")

class DeleteCommentView(APIView):
    def get(self, request, pk):
        comment = get_object_or_404(Comment, id=pk)
        return render(request, "comments/delete_comment.html", {"comment": comment})

    def post(self, request, pk):
        comment = get_object_or_404(Comment, id=pk)
        comment.delete()
        return redirect("home")
