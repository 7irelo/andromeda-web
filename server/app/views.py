from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.db.models import Q
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Post, Comment, User
from .forms import PostForm, UserForm, MyUserCreationForm
from .serializers import UserSerializer, PostSerializer, CommentSerializer
import jwt, datetime

class RegisterView(APIView):
    def post(self, request):
        serializer = UserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

class LoginView(APIView):
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')

        user = User.objects.filter(email=email).first()
        if not user or not user.check_password(password):
            raise AuthenticationFailed('Invalid credentials')

        payload = {
            'id': user.id,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=60),
            'iat': datetime.datetime.utcnow()
        }
        token = jwt.encode(payload, 'secret', algorithm='HS256')

        response = Response()
        response.set_cookie(key='jwt', value=token, httponly=True)
        response.data = {'jwt': token}
        return response

class UserView(APIView):
    def get(self, request):
        token = request.COOKIES.get('jwt')
        if not token:
            raise AuthenticationFailed('Unauthenticated')

        try:
            payload = jwt.decode(token, 'secret', algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed('Unauthenticated')

        user = User.objects.filter(id=payload['id']).first()
        serializer = UserSerializer(user)
        return Response(serializer.data)

class UpdateUserView(APIView):
    def get(self, request):
        user = request.user
        form = UserForm(instance=user)
        return render(request, "profile/update_user.html", {"form": form})
    
    def post(self, request):
        user = request.user
        form = UserForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            return redirect("user-profile", pk=user.id)
        return render(request, "profile/update_user.html", {"form": form})

class LogoutView(APIView):
    def post(self, request):
        response = Response()
        response.delete_cookie('jwt')
        response.data = {'message': 'success'}
        return response

class HomeView(APIView):
    def get(self, request):
        q = request.GET.get("q", "")
        posts = Post.objects.filter(Q(user__name__icontains=q) | Q(text__icontains=q))
        serializer = PostSerializer(posts, many=True)
        return Response(serializer.data)

class PostView(APIView):
    def get(self, request, pk):
        post = Post.objects.get(id=pk)
        comments = post.comment_set.all().order_by("created")
        participants = post.participants.all()
        serializer = PostSerializer(post)
        return Response(serializer.data)

    def post(self, request, pk):
        post = Post.objects.get(id=pk)
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
        post = Post.objects.get(id=pk)
        form = PostForm(instance=post)
        return render(request, "posts/update_post.html", {"form": form, "post": post})
        
    def post(self, request, pk):
        post = Post.objects.get(id=pk)
        post.text = request.data.get("text")
        post.save()
        return redirect("home")

class DeletePostView(APIView):
    def get(self, request, pk):
        post = Post.objects.get(id=pk)
        return render(request, "posts/delete_post.html", {"post": post})
        
    def post(self, request, pk):
        post = Post.objects.get(id=pk)
        post.delete()
        return redirect("home")

class DeleteCommentView(APIView):
    def get(self, request, pk):
        comment = Comment.objects.get(id=pk)
        return render(request, "comments/delete_comment.html", {"comment": comment})

    def post(self, request, pk):
        comment = Comment.objects.get(id=pk)
        comment.delete()
        return redirect("home")
