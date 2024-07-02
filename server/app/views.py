from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from users.models import User
from .serializers import UserSerializer
from posts.models import Post
from posts.serializers import PostSerializer
import jwt
import datetime

class RegisterView(APIView):
    def post(self, request):
        serializer = UserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

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
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm='HS256')

        response = Response()
        response.set_cookie(
            key='jwt',
            value=token,
            httponly=True,
            secure=settings.SECURE_COOKIE,
            samesite='Lax'
        )
        response.data = {'jwt': token}
        return response

class LogoutView(APIView):
    def post(self, request):
        response = Response({'message': 'success'})
        response.delete_cookie('jwt')
        return response
