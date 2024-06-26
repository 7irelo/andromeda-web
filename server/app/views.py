from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.db.models import Q
from rest_framework.decorators import api_view
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.Views import APIView
from .models import Post, Comment, User
from .forms import PostForm, UserForm, MyUserCreationForm
from .serializers import UserSerializer
import jwt, datetime

class RegisterView(APIView):
    def post(self, request):
        serializer = UserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

class LoginView(APIView):
    def post(self, request):
        email = request.data['email']
        password = request.data['password']
        user = User.objects.filter(email=email)
        if user is None:
            raise AuthenticationFailed('User not found')
        if not user.check_password(password):
            raise AuthenticationFailed('Incorrect password')
        payload = {
            'id': user.id,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=60),
            'iat': datetime.datetime.utcnow()
        }
        token = jwt.encode(payload, 'secret', algorithm='HS256').decode('utf-8')
        serializer = UserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        response = Response()
        response.set_cookie(key='jwt', value=token, httponly=True)
        response.data = {
            'jwt': token
        }
        return response

class UserView(APIView):
    def get(self, request):
        token = request.COOKIES.get('jwt')
        if not token:
            raise AuthenticationFailed('Unauthenticated')
        try:
            payload = jwt.decode(token, 'secret', algorithm=['HS256']
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed('Unauthenticated')
        user = User.objects.filter(id=payload['id']).first()
        
        posts = user.post_set.all()
        comments = user.comment_set.all()
        context = {"user": user, "posts": posts, "comments": comments}
        serializer = UserSerializer(user)
        return Response(serializer.data)
class UpdateUser(APIView):
    def get(self, request):
        user = request.user
        form = UserForm(instance=user)
        context = {"form": form}
        return render(request, "profile/update_user.html", context)
    
    def post(self, request):
        form = UserForm(request.POST, instance=user)
        if form.is_valid:
            form.save()
            return redirect("user-profile", pk=user.id)

        context = {"form": form}
        return render(request, "profile/update_user.html", context)
        
class LogoutView(APIView):
    def post(self, request):
        response = Response()
        response.delete_cookie('jwt')
        response.data = {
            'message': success
        }

class HomeView(APIView):
    def get(self, request):
        q = request.GET.get("q") if request.GET.get("q") != None else ""

        posts = Post.objects.filter(Q(user__name__icontains=q) | Q(text__icontains=q))
  
        post_count = post.count()
        comments = Comment.objects.filter(Q(post___text___icontains=q))

        context = {"posts": posts, "post_count": post_count, "comments": comments}
        serializer = PostSerializer(posts, many=True)
        return Response(serializer.data)

class PostView(APIView):
    def get(self, request, pk):
        post = Post.objects.get(id=pk)
        comments = post.comment_set.all().order_by("created")
        participants = post.participants.all()
        context = {"post": post, "comments": comments, "participants": participants}
        serializer = PostSerializer(post, many=False)
        return Response(serializer.data)

    def post(self, request, pk):
        post = Post.objects.get(id=pk)
        comments = Comment.objects.create(
            user=request.user,
            post=post,
            text=request.POST.get("text")
        )
        post.participants.add(request.user)
        return redirect("post", pk=post.id)
class CreatePost(APIView):
    def get(self, request):
        form = PostForm()
        context = {"form": form}
        serializer = PostSerializer(post, many=False)
        return Response(serializer.data)
        
    def post(self, request):
        post_text = request.POST.get("text")
        Post.objects.create(
            host=request.user,
            text=post_text,
        )
        return redirect("home")

class UpdatePost(APIView):
    def get(request, pk):
        post = Post.objects.get(id=pk)
        form = PostForm(instance=post)
        context = {"form": form, "topics": topics, "post":post}
        serializer = PostSerializer(post, many=False)
        return Response(serializer.data)
        
    def post(self, request, pk):
        post = Post.objects.get(id=pk)
        post.text = request.POST.get("text")
        post.save()
        return redirect("home")

class DeletePost(APIView):
    def get(request, pk):
        post = Post.objects.get(id=pk)
        serializer = PostSerializer(post, many=False)
        return Response(serializer.data)
        
    def post(self, request):
        post = Post.objects.get(id=pk)
        post.delete()
        return redirect("home")

class DeleteComment(APIView):
    def get(request, pk):
        comment = Comment.objects.get(id=pk)
        serializer = CommentSerializer(comment, many=False)
        return Response(serializer.data)

    def post(self, request):
        comment = Comment.objects.get(id=pk)
        comment.delete()
        return redirect("home")
