from django.contrib import messages
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.Views import APIView
from app.models import User
from .serializers import UserSerializer

class FriendsView(APIView):
    def get(self, request):
        token = request.COOKIES.get('jwt')
        if not token:
            raise AuthenticationFailed('Unauthenticated')
        try:
            payload = jwt.decode(token, 'secret', algorithm=['HS256']
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed('Unauthenticated')
        
        user = User.objects.filter(id=payload['id']).first()
        serializer = UserSerializer(user)
        return Response(serializer.data)
