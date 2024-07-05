from django.contrib import messages
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.views import APIView
from users.models import User
from users.serializers import UserSerializer
import jwt
from django.conf import settings

class FriendsView(APIView):
    def get(self, request):
        # Retrieve the JWT token from cookies
        token = request.COOKIES.get('jwt')
        if not token:
            raise AuthenticationFailed('Unauthenticated: No token provided')
        
        try:
            # Decode the JWT token to get the payload
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed('Unauthenticated: Token has expired')
        except jwt.InvalidTokenError:
            raise AuthenticationFailed('Unauthenticated: Invalid token')

        # Retrieve the user based on the ID in the payload
        user = User.objects.filter(id=payload.get('id')).first()
        if not user:
            raise AuthenticationFailed('Unauthenticated: User not found')

        # Serialize the user data
        serializer = UserSerializer(user)
        return Response(serializer.data)
