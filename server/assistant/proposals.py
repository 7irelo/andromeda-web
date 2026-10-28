"""
Approving or rejecting a proposal: the only way an AI-initiated write happens.

Single-use (the row is locked and must still be pending), owner-only,
time-limited, and re-validated against the permissions in force right now.
Every committed write is audited with the model, prompt version, tool-call
trace and approver.
"""
from django.db import transaction
from django.utils import timezone

from . import runner, tools
from .models import AIWriteAudit, AssistantRun, AssistantStep, Proposal


class DecisionError(Exception):
    def __init__(self, detail, status):
        super().__init__(detail)
        self.detail = detail
        self.status = status


def _trace(proposal):
    if proposal.run_id is None:
        return [{'tool': proposal.tool, 'source': proposal.source}]
    steps = proposal.run.steps.filter(kind__in=[AssistantStep.KIND_TOOL, AssistantStep.KIND_MODEL]).order_by('index')
    trace = []
    for s in steps:
        if s.kind == AssistantStep.KIND_TOOL:
            trace.append({'tool': s.tool_name, 'args': s.tool_args, 'error': s.is_error})
        else:
            trace.append({'model': s.model, 'calls': [c.get('name') for c in (s.output or {}).get('tool_calls', [])]})
    return trace[:100]


def decide(proposal_id, user, approve):
    """Approve or reject the user's own pending proposal. Returns the updated proposal."""
    with transaction.atomic():
        proposal = (Proposal.objects.select_for_update().select_related('run', 'token')
                    .filter(pk=proposal_id, owner=user).first())
        if proposal is None:
            raise DecisionError('Not found.', 404)
        if proposal.status != Proposal.STATUS_PENDING:
            raise DecisionError(f'This proposal was already {proposal.status}.', 409)
        if proposal.run_id:
            # Serialise with the runner pausing the run (see runner._await).
            AssistantRun.objects.select_for_update().filter(pk=proposal.run_id).first()
        now = timezone.now()
        if proposal.is_expired:
            proposal.status, proposal.decided_at = Proposal.STATUS_EXPIRED, now
            proposal.save(update_fields=['status', 'decided_at'])
            runner.record_decision(proposal)
            if proposal.run_id:
                proposal.run.refresh_from_db()
                runner.resume(proposal.run)
            expired = True
        else:
            expired = False
            proposal.decided_at, proposal.decided_by = now, user
            if not approve:
                proposal.status = Proposal.STATUS_REJECTED
            else:
                try:
                    with transaction.atomic():
                        object_type, object_id, result = tools.commit(proposal, user)
                        AIWriteAudit.objects.create(
                            user=proposal.owner, proposal=proposal, run=proposal.run, source=proposal.source,
                            tool=proposal.tool, arguments=proposal.arguments,
                            model=proposal.model or (f'mcp:{proposal.token.name}' if proposal.token_id else ''),
                            prompt_version=proposal.prompt_version, tool_calls=_trace(proposal), approved_by=user,
                            object_type=object_type, object_id=object_id)
                    proposal.status, proposal.result = Proposal.STATUS_APPROVED, result
                except tools.ToolError as exc:
                    proposal.status, proposal.error = Proposal.STATUS_FAILED, str(exc)[:300]
            proposal.save(update_fields=['status', 'decided_at', 'decided_by', 'result', 'error'])
            runner.record_decision(proposal)
            if proposal.run_id:
                proposal.run.refresh_from_db()
                runner.resume(proposal.run)
    if expired:
        raise DecisionError('This proposal expired. Ask the assistant again.', 410)
    return proposal
