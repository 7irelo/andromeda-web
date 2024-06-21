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

class RegisterPage(APIView):
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

@api_view(['GET'])
def loginPage(request):
    page = "login"

    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        email = request.POST.get("email").lower()
        password = request.POST.get("password")

        try:
            user = User.objects.get(email=email)
            user = authenticate(request, email=email, password=password)
            if user is not None:
                login(request, user)
                return redirect("home")
            else:
                messages.error(request, "incorrect password")
        except:
            messages.error(request, "Incorrect username")


    context = {"page": page}
    return render(request, 'base/login_register.html', context)

@api_view(['GET'])
def logoutUser(request):
    logout(request)
    return redirect("home")

@api_view(['GET'])
def registerPage(request):
    form = MyUserCreationForm()
    if request.method == "POST":
        form = MyUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.username = user.username.lower()
            user.save()
            login(request, user)
            return redirect("home")
        else:
            messages.error(request, "An error occured during registration")
    context = {"form": form}
    return render(request, 'base/login_register.html', context)

@api_view(['GET'])
def home(request):
    q = request.GET.get("q") if request.GET.get("q") != None else ""

    posts = Post.objects.filter(Q(user__name__icontains=q) | Q(text__icontains=q))
  
    post_count = post.count()
    comments = Comment.objects.filter(Q(post___text___icontains=q))

    context = {"posts": posts, "post_count": post_count, "comments": comments}
    serializer = PostSerializer(posts, many=True)
    return Response(serializer.data)

@api_view(['GET'])
def post(request, pk):
    post = Post.objects.get(id=pk)
    comments = post.comment_set.all().order_by("created")
    participants = post.participants.all()

    if request.method == "POST":
    comments = Comment.objects.create(
            user=request.user,
            post=post,
            text=request.POST.get("text")
        )
        post.participants.add(request.user)
        return redirect("post", pk=post.id)
    context = {"post": post, "comments": comments, "participants": participants}
    serializer = PostSerializer(post, many=False)
    return Response(serializer.data)

@api_view(['GET'])
def userProfile(request, pk):
    user = User.objects.get(id=pk)
    posts = user.post_set.all()
    comments = user.comment_set.all()
    context = {"user": user, "posts": posts, "comments": comments}
    serializer = PostSerializer(posts, many=True)
    return Response(serializer.data)

@api_view(['GET'])
@login_required(login_url="login")
def createPost(request):
  form = PostForm()
  if request.method == "POST":
      post_text = request.POST.get("text")
            Post.objects.create(
                host=request.user,
                text=post_text,
            )

        #form #PostForm(request.POST)
        #if form.is_valid():
            #post = form.save(commit=False)
            #post.host = request.user
            #post.save()
            return redirect("home")
    context = {"form": form}
    serializer = PostSerializer(post, many=False)
    return Response(serializer.data)

@api_view(['GET'])
@login_required(login_url="login")
def updatePost(request, pk):
    post = Post.objects.get(id=pk)
    form = PostForm(instance=post)
    if request.method == "POST":
        post.text = request.POST.get("text")
        post.save()

        return redirect("home")
    context = {"form": form, "topics": topics, "post":post}
    serializer = PostSerializer(post, many=False)
    return Response(serializer.data)

@api_view(['GET'])
@login_required(login_url="login")
def deletePost(request, pk):
    post = Post.objects.get(id=pk)
    if request.method == "POST":
        post.delete()
        return redirect("home")

    serializer = PostSerializer(post, many=False)
    return Response(serializer.data)

@api_view(['GET'])
@login_required(login_url="login")
def deleteComment(request, pk):
    comment = Comment.objects.get(id=pk)
    if request.method == "POST":
        comment.delete()
        return redirect("home")

    serializer = CommentSerializer(comment, many=False)
    return Response(serializer.data)

@api_view(['GET'])
@login_required(login_url="login")
def updateUser(request):
    user = request.user
    form = UserForm(instance=user)
    if request.method == "POST":
        form = UserForm(request.POST, instance=user)
        if form.is_valid:
            form.save()
            return redirect("user-profile", pk=user.id)
    context = {"form": form}
    return render(request, "profile/update_user.html", context)
