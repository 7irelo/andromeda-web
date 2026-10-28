from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import services, targets
from .models import Appeal, ModerationAction, ModerationCase, Report


class ReportSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = ['id', 'reason', 'details', 'created_at']


class ActionSerializer(serializers.ModelSerializer):
    moderator_username = serializers.CharField(source='moderator.username', default=None, read_only=True)

    class Meta:
        model = ModerationAction
        fields = ['id', 'action', 'note', 'moderator_username', 'automated_by', 'created_at']


class AppealSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appeal
        fields = ['id', 'message', 'status', 'created_at', 'decided_at']


class ModerationCaseSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source='author.username', default=None, read_only=True)
    author_id = serializers.IntegerField(read_only=True)
    content = serializers.SerializerMethodField()
    reports = serializers.SerializerMethodField()
    actions = ActionSerializer(many=True, read_only=True)
    appeal = serializers.SerializerMethodField()

    class Meta:
        model = ModerationCase
        fields = ['id', 'content_type', 'object_id', 'author_id', 'author_username', 'content', 'snapshot',
                  'decision', 'categories', 'confidence', 'reason', 'model', 'stages', 'degraded', 'source',
                  'report_count', 'reports', 'actions', 'appeal', 'resolved', 'created_at']

    def get_content(self, obj):
        _, _, text = targets.load(obj.content_type, obj.object_id)
        return text[:2000]

    def get_reports(self, obj):
        return ReportSummarySerializer(obj.reports.all()[:20], many=True).data

    def get_appeal(self, obj):
        a = getattr(obj, 'appeal', None)
        return AppealSerializer(a).data if a else None


class ResolveSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['approve', 'remove', 'restore', 'warn', 'suspend', 'ban', 'dismiss'])
    note = serializers.CharField(max_length=500, required=False, allow_blank=True)
    days = serializers.IntegerField(required=False, min_value=1, max_value=services.MAX_SUSPENSION_DAYS)


class AppealDecisionSerializer(serializers.Serializer):
    restore = serializers.BooleanField()
    note = serializers.CharField(max_length=500, required=False, allow_blank=True)


class ModerationCaseViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Staff-only review queue. Every action is written to the audit log."""

    serializer_class = ModerationCaseSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = ModerationCase.objects.select_related('author', 'appeal').prefetch_related('actions__moderator')
        params = self.request.query_params
        if params.get('all') != 'true':
            qs = qs.filter(resolved=False)
        if params.get('source') in (ModerationCase.SOURCE_AUTO, ModerationCase.SOURCE_REPORT):
            qs = qs.filter(source=params['source'])
        if params.get('type') in dict(ModerationCase.TYPE_CHOICES):
            qs = qs.filter(content_type=params['type'])
        if params.get('appeals') == 'true':
            qs = qs.filter(appeal__status=Appeal.STATUS_OPEN)
        return qs.order_by('-report_count', '-created_at')

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        case = self.get_object()
        body = ResolveSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        d = body.validated_data
        services.resolve(case, request.user, d['action'], d.get('note', ''), d.get('days'))
        case.refresh_from_db()
        return Response(ModerationCaseSerializer(case).data)

    @action(detail=True, methods=['post'], url_path='appeal')
    def decide_appeal(self, request, pk=None):
        case = self.get_object()
        a = getattr(case, 'appeal', None)
        if a is None:
            raise NotFound('No appeal on this case.')
        body = AppealDecisionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        services.decide_appeal(a, request.user, body.validated_data['restore'], body.validated_data.get('note', ''))
        case.refresh_from_db()
        return Response(ModerationCaseSerializer(case).data)


class ReportSerializer(serializers.Serializer):
    content_type = serializers.ChoiceField(choices=[c for c, _ in ModerationCase.TYPE_CHOICES])
    object_id = serializers.IntegerField(min_value=1)
    reason = serializers.ChoiceField(choices=[r for r, _ in Report.REASON_CHOICES])
    details = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class ReportView(APIView):
    """Report something you can see. Rate-limited; one report per member per item."""

    throttle_classes = [*api_settings.DEFAULT_THROTTLE_CLASSES, ScopedRateThrottle]
    throttle_scope = 'report'

    def get(self, request):
        return Response({'reasons': [{'key': k, 'label': v} for k, v in Report.REASON_CHOICES]})

    def post(self, request):
        body = ReportSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        d = body.validated_data
        services.file_report(request.user, d['content_type'], d['object_id'], d['reason'], d.get('details', ''))
        return Response({'detail': "Thanks. We'll review it and let you know when we have."},
                        status=status.HTTP_201_CREATED)


class MyCasesView(APIView):
    """Decisions about the member's own content, so they can see why and appeal."""

    def get(self, request):
        cases = (ModerationCase.objects.filter(author=request.user)
                 .filter(decision='remove') | ModerationCase.objects.filter(author=request.user,
                                                                            actions__action='remove'))
        rows = []
        for c in cases.distinct().select_related('appeal').order_by('-created_at')[:50]:
            a = getattr(c, 'appeal', None)
            rows.append({'id': c.id, 'content_type': c.content_type, 'object_id': c.object_id,
                         'snapshot': (c.snapshot or targets.load(c.content_type, c.object_id)[2])[:500],
                         'categories': c.categories, 'created_at': c.created_at,
                         'appeal': AppealSerializer(a).data if a else None})
        return Response(rows)


class AppealView(APIView):
    throttle_classes = [*api_settings.DEFAULT_THROTTLE_CLASSES, ScopedRateThrottle]
    throttle_scope = 'report'

    def post(self, request, case_id):
        case = ModerationCase.objects.filter(pk=case_id, author=request.user).first()
        if case is None:
            raise NotFound()
        services.appeal(request.user, case, str(request.data.get('message', '')))
        return Response({'detail': 'Appeal sent. A moderator will look at it.'}, status=status.HTTP_201_CREATED)
