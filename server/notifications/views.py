from urllib.parse import urlparse

from django.conf import settings
from rest_framework import generics, serializers, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification, NotificationPreference, PushSubscription
from .serializers import NotificationSerializer
from .service import CATEGORIES, preferences, push_enabled


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        qs = Notification.objects.filter(recipient=self.request.user, in_app=True)
        unread_only = self.request.query_params.get('unread')
        if unread_only == 'true':
            qs = qs.filter(is_read=False)
        return qs.select_related('sender')


@api_view(['POST'])
def mark_all_read(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return Response({'status': 'all_read'})


@api_view(['POST'])
def mark_read(request, pk):
    Notification.objects.filter(id=pk, recipient=request.user).update(is_read=True)
    return Response({'status': 'read'})


@api_view(['GET'])
def unread_count(request):
    count = Notification.objects.filter(recipient=request.user, is_read=False, in_app=True).count()
    return Response({'unread_count': count})


class ChannelSerializer(serializers.Serializer):
    in_app = serializers.BooleanField(required=False)
    push = serializers.BooleanField(required=False)
    email = serializers.BooleanField(required=False)


class PreferencesView(APIView):
    """Per-category notification channels, the daily digest and the weekly listings email."""

    def _body(self, user):
        pref = NotificationPreference.objects.filter(user=user).first()
        current = preferences(user)
        return {
            'categories': [{'key': k, 'label': v['label'], 'locked': bool(v.get('locked')), **current[k]}
                           for k, v in CATEGORIES.items()],
            'email_digest': pref.email_digest if pref else NotificationPreference.DIGEST_DAILY,
            'listing_digest': pref.listing_digest if pref else False,
            'push_available': push_enabled(),
        }

    def get(self, request):
        return Response(self._body(request.user))

    def patch(self, request):
        pref, _ = NotificationPreference.objects.get_or_create(user=request.user)
        channels = dict(pref.channels)
        categories = request.data.get('categories') or {}
        if not isinstance(categories, dict):
            return Response({'categories': 'Expected an object.'}, status=status.HTTP_400_BAD_REQUEST)
        for key, value in categories.items():
            if key not in CATEGORIES:
                continue
            body = ChannelSerializer(data=value)
            body.is_valid(raise_exception=True)
            channels[key] = {**channels.get(key, {}), **body.validated_data}
        pref.channels = channels
        if request.data.get('email_digest') in (NotificationPreference.DIGEST_OFF, NotificationPreference.DIGEST_DAILY):
            pref.email_digest = request.data['email_digest']
        if isinstance(request.data.get('listing_digest'), bool):
            pref.listing_digest = request.data['listing_digest']
        pref.save()
        return Response(self._body(request.user))


class PushSubscriptionSerializer(serializers.Serializer):
    endpoint = serializers.URLField(max_length=1000)
    keys = serializers.DictField(child=serializers.CharField(max_length=200))

    def validate_endpoint(self, value):
        # The server POSTs to this URL, so only HTTPS push services we know are accepted.
        host = (urlparse(value).hostname or '').lower()
        known = any(host == d or host.endswith('.' + d) for d in settings.WEB_PUSH_ALLOWED_HOSTS)
        if not value.startswith('https://') or not known:
            raise serializers.ValidationError('Unsupported push service.')
        return value

    def validate_keys(self, value):
        if not value.get('p256dh') or not value.get('auth'):
            raise serializers.ValidationError('Missing keys.')
        return value


class PushSubscriptionView(APIView):
    def get(self, request):
        return Response({'public_key': settings.VAPID_PUBLIC_KEY if push_enabled() else None})

    def post(self, request):
        body = PushSubscriptionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        d = body.validated_data
        PushSubscription.objects.update_or_create(endpoint=d['endpoint'], defaults={
            'user': request.user, 'p256dh': d['keys']['p256dh'], 'auth': d['keys']['auth'],
            'user_agent': (request.META.get('HTTP_USER_AGENT') or '')[:200]})
        return Response(status=status.HTTP_201_CREATED)

    def delete(self, request):
        PushSubscription.objects.filter(user=request.user, endpoint=str(request.data.get('endpoint', ''))).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
