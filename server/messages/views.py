from django.db.models import Q
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Chat, Message
from .serializers import MessageSerializer
import jwt

class ChatView(APIView):
    def get(self, request, pk):
        try:
            chat = Chat.objects.get(id=pk)
        except Chat.DoesNotExist:
            return Response({'error': 'Chat not found'}, status=404)
        
        messages = chat.message_set.all().order_by("created")
        participants = chat.participants.all()
        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data)

    def post(self, request, pk):
        try:
            chat = Chat.objects.get(id=pk)
        except Chat.DoesNotExist:
            return Response({'error': 'Chat not found'}, status=404)
        
        message = Message.objects.create(
            user=request.user,
            chat=chat,
            text=request.data.get("text")  # Use request.data for DRF views
        )
        chat.participants.add(request.user)
        return Response({'message': 'Message created successfully'}, status=201)

    def put(self, request, pk):
        try:
            message = Message.objects.get(id=pk)
        except Message.DoesNotExist:
            return Response({'error': 'Message not found'}, status=404)
        
        message.text = request.data.get("text")  # Use request.data for DRF views
        message.save()
        return Response({'message': 'Message updated successfully'})

    def delete(self, request, pk):
        try:
            message = Message.objects.get(id=pk)
        except Message.DoesNotExist:
            return Response({'error': 'Message not found'}, status=404)
        
        message.delete()
        return Response({'message': 'Message deleted successfully'})
