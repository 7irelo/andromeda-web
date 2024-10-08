from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import PermissionDenied
from .models import User
from .serializers import UserSerializer
from posts.models import Post
from posts.serializers import PostSerializer

class UserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, username):
        user = User.nodes.get_or_none(username=username)
        if user is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = UserSerializer(user)
        return Response(serializer.data)

    def put(self, request, username):
        user = User.nodes.get_or_none(username=username)
        if user is None or user != request.user:
            raise PermissionDenied("You do not have permission to perform this action.")

        serializer = UserSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, username):
        user = User.nodes.get_or_none(username=username)
        if user is None or user != request.user:
            raise PermissionDenied("You do not have permission to perform this action.")
        
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class FriendsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, username):
        user = User.nodes.get_or_none(username=username)
        if user is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        friends = user.friends.all()
        serializer = UserSerializer(friends, many=True)
        return Response(serializer.data)

    def post(self, request, username):
        user = User.nodes.get_or_none(username=username)
        if user is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if user == request.user:
            return Response({"detail": "You cannot add yourself as a friend."}, status=status.HTTP_400_BAD_REQUEST)

        request.user.friends.connect(user)
        return Response({"detail": "Friend added successfully."}, status=status.HTTP_201_CREATED)

    def delete(self, request, username):
        user = User.nodes.get_or_none(username=username)
        if user is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not request.user.friends.is_connected(user):
            return Response({"detail": "Friendship does not exist."}, status=status.HTTP_400_BAD_REQUEST)

        request.user.friends.disconnect(user)
        return Response({"detail": "Friend removed successfully."}, status=status.HTTP_204_NO_CONTENT)

class UserPostsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, username):
        user = User.nodes.get_or_none(username=username)
        if user is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        posts = Post.objects.filter(creator=user)
        serializer = PostSerializer(posts, many=True)
        return Response(serializer.data)
