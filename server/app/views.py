from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from .models import User
from .serializers import UserSerializer
from posts.models import Post
from posts.serializers import PostSerializer
import jwt
import datetime

class RegisterView(APIView):
    """
    API view to register a new user.
    """
    def post(self, request):
        serializer = UserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class LoginView(APIView):
    """
    API view to handle user login and JWT token creation.
    """
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
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm='HS256')

        response = Response()
        response.set_cookie(key='jwt', value=token, httponly=True)
        response.data = {'jwt': token}
        return response

class LogoutView(APIView):
    """
    API view to handle user logout and delete JWT token cookie.
    """
    def post(self, request):
        response = Response({'message': 'success'})
        response.delete_cookie('jwt')
        return response

class HomeView(APIView):
    """
    API view to search and retrieve posts.
    """
    def get(self, request):
        """
        Retrieve posts based on search query (q).
        """
        q = request.GET.get("q", "")
        posts = Post.objects.filter(Q(user__name__icontains=q) | Q(text__icontains=q))
        serializer = PostSerializer(posts, many=True)
        return Response(serializer.data)
