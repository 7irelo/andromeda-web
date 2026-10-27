from django.db import transaction
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from .models import STATUS_OK, STATUS_REMOVED, ModerationAction, ModerationCase
from .tasks import _load


class ModerationCaseSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source='author.username', default=None, read_only=True)
    content = serializers.SerializerMethodField()

    class Meta:
        model = ModerationCase
        fields = ['id', 'content_type', 'object_id', 'author_username', 'content', 'decision', 'categories',
                  'confidence', 'reason', 'model', 'stages', 'degraded', 'resolved', 'created_at']

    def get_content(self, obj):
        _, _, text = _load(obj.content_type, obj.object_id)
        return text[:2000]


class ResolveSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['approve', 'remove', 'restore'])
    note = serializers.CharField(max_length=500, required=False, allow_blank=True)


class ModerationCaseViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Staff-only review queue. Every action is written to the audit log."""

    serializer_class = ModerationCaseSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = ModerationCase.objects.select_related('author')
        if self.request.query_params.get('all') != 'true':
            qs = qs.filter(resolved=False)
        return qs

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        case = self.get_object()
        body = ResolveSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        act = body.validated_data['action']
        obj, _, _ = _load(case.content_type, case.object_id)
        if obj is None:
            raise ValidationError({'detail': 'The content no longer exists.'})
        with transaction.atomic():
            new_status = STATUS_REMOVED if act == 'remove' else STATUS_OK
            type(obj).objects.filter(pk=obj.pk).update(moderation_status=new_status)
            ModerationAction.objects.create(case=case, moderator=request.user, action=act,
                                            note=body.validated_data.get('note', ''))
            case.resolved = True
            case.save(update_fields=['resolved'])
        return Response({'status': new_status})
