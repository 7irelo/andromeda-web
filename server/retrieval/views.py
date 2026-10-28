from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core import ai_client
from core.search import CONTENT, _serializers

from . import documents, hybrid

KINDS = ['posts', 'listings', 'groups', 'pages', 'videos']
ASK_SOURCES = 8


class SemanticQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=200, trim_whitespace=True)
    type = serializers.ChoiceField(choices=['all'] + KINDS, default='all')


def _serialize(hits, request):
    registry = _serializers()
    by_kind = {}
    for h in hits:
        by_kind.setdefault(h.kind, []).append(h.id)
    objects = {}
    for kind, ids in by_kind.items():
        serializer = registry[kind][1]
        # Re-read through the visibility queryset: hits are ids, not permissions.
        for obj in CONTENT[kind][0](request.user).filter(pk__in=ids):
            objects[(kind, obj.pk)] = serializer(obj, context={'request': request}).data
    return [{'type': h.kind, 'score': h.score, 'matched_by': h.sources, 'item': objects[(h.kind, h.id)]}
            for h in hits if (h.kind, h.id) in objects]


class SemanticSearchView(APIView):
    """Hybrid search over everything the viewer can see, ranked as one list."""

    throttle_classes = [*api_settings.DEFAULT_THROTTLE_CLASSES, ScopedRateThrottle]
    throttle_scope = 'search'

    def get(self, request):
        params = SemanticQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        q, kind = params.validated_data['q'], params.validated_data['type']
        if len(q) < 2:
            raise ValidationError({'q': 'Type at least 2 characters.'})
        kinds = KINDS if kind == 'all' else [kind]
        plan, hits = hybrid.search(request.user, q, kinds, limit=30)
        return Response({
            'query': q,
            'understood_as': {'query': plan.query, 'types': plan.types, 'since_days': plan.since_days,
                              'author': plan.author} if plan.rewritten else None,
            'semantic': plan.vector is not None,
            'results': _serialize(hits, request),
        })


class AskSerializer(serializers.Serializer):
    question = serializers.CharField(min_length=3, max_length=500, trim_whitespace=True)


LINKS = {'posts': '/posts/{id}', 'listings': '/marketplace/{id}', 'groups': '/groups/{id}',
         'pages': '/pages/{id}', 'videos': '/watch/{id}'}


class AskView(APIView):
    """
    "Ask Andromeda": a grounded answer built only from content the viewer can see.

    Retrieval runs as the viewer, so the answer model is never shown anything
    the viewer couldn't open themselves.
    """

    throttle_classes = [*api_settings.DEFAULT_THROTTLE_CLASSES, ScopedRateThrottle]
    throttle_scope = 'ai'

    def post(self, request):
        body = AskSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        question = body.validated_data['question']
        if request.user.ai_opt_out:
            return Response({'detail': 'You have turned off AI features in your settings.'}, status=403)
        if not ai_client.enabled():
            return Response({'detail': 'Ask Andromeda is not available right now.'}, status=503)
        plan = hybrid.plan_query(question, request.user.id, rewrite=True)
        _, hits = hybrid.search(request.user, question, KINDS, plan=plan, limit=ASK_SOURCES)
        sources, meta = [], {}
        for h in hits:
            doc = documents.load(h.kind, h.id)
            if doc is None:
                continue
            sid = f'{h.kind}:{h.id}'
            sources.append({'id': sid, 'kind': h.kind.rstrip('s'), 'title': doc.title[:200],
                            'author': doc.author, 'created_at': doc.created_at, 'text': doc.text[:6000]})
            meta[sid] = {'type': h.kind, 'id': h.id, 'title': doc.title[:120] or h.kind.rstrip('s').title(),
                         'author': doc.author, 'url': LINKS[h.kind].format(id=h.id)}
        try:
            res = ai_client.call('/v1/ask', {'question': question, 'viewer': request.user.username,
                                             'sources': sources}, user_id=request.user.id)
        except ai_client.AIRejected as exc:
            return Response({'detail': exc.detail}, status=exc.status)
        except ai_client.AIUnavailable:
            return Response({'detail': 'Ask Andromeda is not available right now.'}, status=503)
        ans = res['answer']
        return Response({
            'abstain': ans['abstain'],
            'answer': ans['answer'],
            'claims': [{'text': c['text'], 'sources': [meta[i] for i in c['source_ids'] if i in meta]}
                       for c in ans['claims']],
            'sources': [meta[s['id']] for s in sources],
        })
