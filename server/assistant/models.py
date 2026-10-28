"""
Andromeda Assistant state.

A run is durable: every model call and tool execution is an append-only
step keyed for idempotency, so a crashed or retried worker resumes from the
last recorded step without repeating completed tool calls. Writes the model
asks for never execute directly; they become proposals the owner approves
in the app, and every committed write leaves an audit row.
"""
import datetime as dt
import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

PROPOSAL_TTL = dt.timedelta(minutes=15)
TOKEN_PREFIX = 'andp_'  # noqa: S105 - a public prefix that identifies Andromeda tokens in leaks
TOKEN_MAX_DAYS = 90


class AssistantRun(models.Model):
    STATUS_QUEUED = 'queued'
    STATUS_RUNNING = 'running'
    STATUS_AWAITING = 'awaiting_approval'
    STATUS_DONE = 'done'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [(STATUS_QUEUED, 'Queued'), (STATUS_RUNNING, 'Running'),
                      (STATUS_AWAITING, 'Awaiting approval'), (STATUS_DONE, 'Done'), (STATUS_FAILED, 'Failed')]
    ACTIVE = (STATUS_QUEUED, STATUS_RUNNING, STATUS_AWAITING)

    PATH_CHOICES = [(p, p) for p in ('search', 'draft_post', 'draft_message', 'summarise', 'agent')]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='assistant_runs', on_delete=models.CASCADE)
    request_text = models.TextField()
    follow_up_of = models.ForeignKey('self', null=True, blank=True, related_name='follow_ups',
                                     on_delete=models.SET_NULL)
    path = models.CharField(max_length=20, choices=PATH_CHOICES, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_QUEUED, db_index=True)
    step_count = models.PositiveIntegerField(default=0)  # model calls made
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    answer = models.TextField(blank=True)
    citations = models.JSONField(default=list, blank=True)
    error = models.CharField(max_length=300, blank=True)
    # A worker's claim on the run, so a redelivered task can't execute it twice at once.
    locked_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'assistant_runs'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['owner', '-created_at'])]

    @property
    def total_tokens(self):
        return self.input_tokens + self.output_tokens


class AssistantStep(models.Model):
    """One model call or tool execution. Append-only: rows are never updated or deleted on their own."""

    KIND_ROUTE = 'route'
    KIND_MODEL = 'model'
    KIND_TOOL = 'tool'
    KIND_CHOICES = [(KIND_ROUTE, 'Route'), (KIND_MODEL, 'Model'), (KIND_TOOL, 'Tool')]

    run = models.ForeignKey(AssistantRun, related_name='steps', on_delete=models.CASCADE)
    index = models.PositiveIntegerField()
    # Idempotency key: 'route', 'model:<n>', 'draft', 'tool:<call id>'.
    key = models.CharField(max_length=120)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    model = models.CharField(max_length=60, blank=True)
    prompt_version = models.CharField(max_length=20, blank=True)
    # Model steps: {'text', 'tool_calls', 'native'}; route steps: the plan.
    output = models.JSONField(default=dict, blank=True)
    tool_name = models.CharField(max_length=40, blank=True)
    tool_args = models.JSONField(default=dict, blank=True)
    # Exactly what the model was shown (already truncated), so replays are byte-identical.
    tool_result = models.TextField(blank=True)
    is_error = models.BooleanField(default=False)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    duration_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'assistant_steps'
        ordering = ['run', 'index']
        constraints = [
            models.UniqueConstraint(fields=['run', 'key'], name='assistant_step_key_unique'),
            models.UniqueConstraint(fields=['run', 'index'], name='assistant_step_index_unique'),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError('Assistant steps are append-only.')
        super().save(*args, **kwargs)


class PersonalAccessToken(models.Model):
    """A credential for external MCP clients. Only the SHA-256 of the token is stored."""

    SCOPE_READ = 'read'
    SCOPE_PROPOSE = 'propose'
    SCOPES = (SCOPE_READ, SCOPE_PROPOSE)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='access_tokens', on_delete=models.CASCADE)
    name = models.CharField(max_length=60)
    token_hash = models.CharField(max_length=64, unique=True)
    prefix = models.CharField(max_length=16)  # shown in settings so a token can be recognised
    scopes = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'assistant_access_tokens'
        ordering = ['-created_at']

    @staticmethod
    def hash(raw):
        return hashlib.sha256(raw.encode()).hexdigest()

    @classmethod
    def issue(cls, user, name, scopes, days):
        raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
        token = cls.objects.create(user=user, name=name, token_hash=cls.hash(raw), prefix=raw[:12],
                                   scopes=sorted(set(scopes)),
                                   expires_at=timezone.now() + dt.timedelta(days=min(days, TOKEN_MAX_DAYS)))
        return token, raw

    @property
    def is_active(self):
        return self.revoked_at is None and self.expires_at > timezone.now()


class Proposal(models.Model):
    """A write the model asked for. Nothing happens until the owner approves it in the app."""

    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_EXPIRED = 'expired'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [(STATUS_PENDING, 'Pending'), (STATUS_APPROVED, 'Approved'), (STATUS_REJECTED, 'Rejected'),
                      (STATUS_EXPIRED, 'Expired'), (STATUS_FAILED, 'Failed')]

    SOURCE_ASSISTANT = 'assistant'
    SOURCE_MCP = 'mcp'

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='assistant_proposals', on_delete=models.CASCADE)
    run = models.ForeignKey(AssistantRun, null=True, blank=True, related_name='proposals', on_delete=models.CASCADE)
    token = models.ForeignKey(PersonalAccessToken, null=True, blank=True, related_name='proposals',
                              on_delete=models.SET_NULL)
    source = models.CharField(max_length=10, default=SOURCE_ASSISTANT)
    call_id = models.CharField(max_length=120, blank=True)
    tool = models.CharField(max_length=40)
    arguments = models.JSONField(default=dict)  # validated arguments, re-validated at approval
    preview = models.JSONField(default=dict)    # exactly what the confirmation card shows
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    model = models.CharField(max_length=60, blank=True)
    prompt_version = models.CharField(max_length=20, blank=True)
    result = models.JSONField(default=dict, blank=True)
    error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name='+',
                                   on_delete=models.SET_NULL)

    class Meta:
        db_table = 'assistant_proposals'
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['run', 'call_id'], condition=Q(run__isnull=False),
                                               name='assistant_proposal_call_unique')]

    def save(self, *args, **kwargs):
        if self.expires_at is None:
            self.expires_at = timezone.now() + PROPOSAL_TTL
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return self.expires_at <= timezone.now()


class AIWriteAudit(models.Model):
    """Who asked, which model and prompt proposed it, what it called, and who approved it."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, related_name='+', on_delete=models.SET_NULL)
    proposal = models.OneToOneField(Proposal, null=True, related_name='audit', on_delete=models.SET_NULL)
    run = models.ForeignKey(AssistantRun, null=True, blank=True, related_name='+', on_delete=models.SET_NULL)
    source = models.CharField(max_length=10)
    tool = models.CharField(max_length=40)
    arguments = models.JSONField(default=dict)
    model = models.CharField(max_length=60, blank=True)
    prompt_version = models.CharField(max_length=20, blank=True)
    tool_calls = models.JSONField(default=list)  # the run's tool-call trace up to this write
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, related_name='+', on_delete=models.SET_NULL)
    object_type = models.CharField(max_length=20)
    object_id = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'assistant_write_audit'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError('Audit rows are append-only.')
        super().save(*args, **kwargs)
