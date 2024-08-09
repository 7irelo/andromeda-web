from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from .models import Chat, Message
from .serializers import ChatSerializer, MessageSerializer

class ChatView(APIView):
    def get(self, request, pk):
        chat = get_object_or_404(Chat.nodes, uid=pk)
        messages = chat.has_message.all().order_by("created")
        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data)

    def post(self, request, pk):
        chat = get_object_or_404(Chat.nodes, uid=pk)
        serializer = MessageSerializer(data=request.data)
        if serializer.is_valid():
            message = serializer.save(user=request.user, chat=chat)
            chat.participants.connect(request.user)
            return Response({'message': 'Message created successfully'}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        message = get_object_or_404(Message.nodes, uid=pk)
        serializer = MessageSerializer(message, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({'message': 'Message updated successfully'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        message = get_object_or_404(Message.nodes, uid=pk)
        message.delete()
        return Response({'message': 'Message deleted successfully'}, status=status.HTTP_204_NO_CONTENT)

class MessagesView(APIView):
    def get(self, request):
        query = request.GET.get("q", "")
        messages = Message.nodes.filter(text__icontains=query).order_by('-updated', '-created')
        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data)
