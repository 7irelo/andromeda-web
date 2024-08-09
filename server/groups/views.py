from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from .models import Group, GroupMessage, GroupMembership
from .serializers import GroupSerializer, GroupMessageSerializer
from users.models import User

class GroupView(APIView):
    def get(self, request, pk):
        group = get_object_or_404(Group.nodes, uid=pk)
        serializer = GroupSerializer(group)
        return Response(serializer.data)

    def post(self, request):
        serializer = GroupSerializer(data=request.data)
        if serializer.is_valid():
            group = serializer.save()
            group.members.connect(request.user, {'is_admin': True})
            return Response({'message': 'Group created successfully'}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        group = get_object_or_404(Group.nodes, uid=pk)
        serializer = GroupSerializer(group, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({'message': 'Group updated successfully'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        group = get_object_or_404(Group.nodes, uid=pk)
        group.delete()
        return Response({'message': 'Group deleted successfully'}, status=status.HTTP_204_NO_CONTENT)

class GroupMessageView(APIView):
    def get(self, request, pk):
        group = get_object_or_404(Group.nodes, uid=pk)
        messages = group.has_message.all().order_by("created")
        serializer = GroupMessageSerializer(messages, many=True)
        return Response(serializer.data)

    def post(self, request, pk):
        group = get_object_or_404(Group.nodes, uid=pk)
        serializer = GroupMessageSerializer(data=request.data)
        if serializer.is_valid():
            message = serializer.save(sender=request.user, group=group)
            return Response({'message': 'Message sent successfully'}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
