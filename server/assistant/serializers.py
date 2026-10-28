from rest_framework import serializers

from .models import AssistantRun, AssistantStep, PersonalAccessToken, Proposal


class ProposalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Proposal
        fields = ['id', 'run', 'source', 'tool', 'preview', 'status', 'result', 'error', 'created_at', 'expires_at',
                  'decided_at']
        read_only_fields = fields


class StepSerializer(serializers.ModelSerializer):
    """Progress only: no tool results, arguments or model internals."""

    class Meta:
        model = AssistantStep
        fields = ['index', 'kind', 'tool_name', 'is_error', 'created_at']
        read_only_fields = fields


class RunSerializer(serializers.ModelSerializer):
    steps = StepSerializer(many=True, read_only=True)
    proposals = ProposalSerializer(many=True, read_only=True)
    total_tokens = serializers.IntegerField(read_only=True)

    class Meta:
        model = AssistantRun
        fields = ['id', 'request_text', 'follow_up_of', 'path', 'status', 'step_count', 'total_tokens', 'cost_usd',
                  'answer', 'citations', 'error', 'steps', 'proposals', 'created_at', 'updated_at']
        read_only_fields = fields


class RunCreateSerializer(serializers.Serializer):
    request = serializers.CharField(min_length=2, max_length=2000, trim_whitespace=True)
    follow_up_of = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class TokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonalAccessToken
        fields = ['id', 'name', 'prefix', 'scopes', 'created_at', 'expires_at', 'last_used_at', 'revoked_at']
        read_only_fields = fields


class TokenCreateSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=1, max_length=60, trim_whitespace=True)
    scopes = serializers.ListField(child=serializers.ChoiceField(choices=PersonalAccessToken.SCOPES), min_length=1,
                                   max_length=2)
    expires_in_days = serializers.IntegerField(min_value=1, max_value=90, default=30)
    password = serializers.CharField(write_only=True, max_length=200)
