from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import NotFound, PermissionDenied
from .models import User
from .serializers import UserSerializer

class UserView(APIView):
    """
    API view to fetch and update user profile.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, username):
        """
        Retrieve details of a specific user by username.
        """
        user = get_object_or_404(User, username=username)
        serializer = UserSerializer(user)
        return Response(serializer.data)

    def put(self, request, username):
        """
        Update details of the authenticated user by username.
        """
        user = get_object_or_404(User, username=username)
        if user != request.user:
            raise PermissionDenied("You do not have permission to perform this action.")

        serializer = UserSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

class UsersView(APIView):
    pass
