from django.contrib import messages
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.views import APIView
from app.models import User
from .serializers import UserSerializer
import jwt  # Ensure jwt library is imported

class FriendsView(APIView):
    def get(self, request):
        # Retrieve the JWT token from cookies
        token = request.COOKIES.get('jwt')
        if not token:
            raise AuthenticationFailed('Unauthenticated')
        
        try:
            # Decode the JWT token to get the payload
            payload = jwt.decode(token, 'secret', algorithms=['HS256'])  # Corrected the spelling of 'algorithms'
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed('Token has expired')
        except jwt.InvalidTokenError:
            raise AuthenticationFailed('Invalid token')

        # Retrieve the user based on the ID in the payload
        user = User.objects.filter(id=payload['id']).first()
        if not user:
            raise AuthenticationFailed('User not found')

        # Serialize the user data
        serializer = UserSerializer(user)
        return Response(serializer.data)
