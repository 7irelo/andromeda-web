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
