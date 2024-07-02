# users/views.py

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import NotFound, PermissionDenied
from .models import User, Friendship
from .serializers import UserSerializer

class UserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, username):
        user = get_object_or_404(User, username=username)
        serializer = UserSerializer(user)
        return Response(serializer.data)

    def put(self, request, username):
        user = get_object_or_404(User, username=username)
        if user != request.user:
            raise PermissionDenied("You do not have permission to perform this action.")

        serializer = UserSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

class FriendsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, username):
        user = get_object_or_404(User, username=username)
        friends = user.friend_set.all()
        serializer = UserSerializer(friends, many=True)
        return Response(serializer.data)

    def post(self, request, username):
        user = get_object_or_404(User, username=username)
        if user == request.user:
            return Response({"detail": "You cannot add yourself as a friend."}, status=status.HTTP_400_BAD_REQUEST)

        friendship, created = Friendship.objects.get_or_create(from_user=request.user, to_user=user)
        if not created:
            return Response({"detail": "Friendship already exists."}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": "Friend added successfully."}, status=status.HTTP_201_CREATED)

    def delete(self, request, username):
        user = get_object_or_404(User, username=username)
        friendship = Friendship.objects.filter(from_user=request.user, to_user=user).first()
        if not friendship:
            return Response({"detail": "Friendship does not exist."}, status=status.HTTP_400_BAD_REQUEST)

        friendship.delete()
        return Response({"detail": "Friend removed successfully."}, status=status.HTTP_204_NO_CONTENT)
