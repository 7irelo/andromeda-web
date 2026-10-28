"""
Executes assistant runs: route, then a fixed workflow or the agent loop.

The AI service plans; tools execute here, as the run's owner. Every model
call and tool execution is appended as a keyed step before the run moves on,
so ``advance`` can be called again at any point (a retry, a crash, an
approval) and it continues from the last recorded step without repeating
completed work. Write tools only ever create proposals; the run pauses until
the owner decides, then resumes.
"""
import datetime as dt
import json
import logging
import re
import time
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F, Max, Q
from django.utils import timezone

from core import ai_client

from . import events, tools
from .models import AssistantRun, AssistantStep, Proposal

logger = logging.getLogger(__name__)

MAX_AGENT_STEPS = getattr(settings, 'ASSISTANT_MAX_STEPS', 8)
MAX_RUN_TOKENS = getattr(settings, 'ASSISTANT_MAX_RUN_TOKENS', 150_000)
MAX_RUN_COST_USD = Decimal(str(getattr(settings, 'ASSISTANT_MAX_RUN_COST_USD', '0.50')))
MAX_CALLS_PER_STEP = 6
MAX_FOLLOW_UPS = 3
LEASE = dt.timedelta(minutes=5)

_URL_RE = re.compile(r'https?://[^\s<>"\')\]]+', re.IGNORECASE)
_CITE_RE = re.compile(r'\[(posts|listings|groups|pages|videos):(\d+)\]')


class RunFailed(Exception):
    pass


class BudgetReached(Exception):
    pass


# ── Steps ────────────────────────────────────────────────────────────────────

def _step(run, key):
    return run.steps.filter(key=key).first()


def _append(run, key, kind, **fields):
    """Append a step, or return the one already recorded under this key."""
    for _ in range(3):
        index = (run.steps.aggregate(m=Max('index'))['m'] if run.steps.exists() else -1)
        try:
            with transaction.atomic():
                return AssistantStep.objects.create(run=run, index=index + 1, key=key, kind=kind, **fields)
        except IntegrityError:
            existing = _step(run, key)
            if existing:
                return existing
    raise RunFailed('Could not record a step.')


def _summary(step):
    """What the panel shows for a step. No tool results or model internals."""
    out = {'index': step.index, 'kind': step.kind, 'is_error': step.is_error}
    if step.kind == AssistantStep.KIND_TOOL:
        out['tool'] = step.tool_name
    return out


def _check_budget(run):
    if run.total_tokens >= MAX_RUN_TOKENS or run.cost_usd >= MAX_RUN_COST_USD:
        raise BudgetReached()


def _model_call(run, key, path, payload):
    """One AI-service call recorded as a step. Rejections fail the run; outages propagate for a retry."""
    existing = _step(run, key)
    if existing:
        return existing
    _check_budget(run)
    started = time.monotonic()
    try:
        data = ai_client.call(path, payload, user_id=run.owner_id)
    except ai_client.AIRejected as exc:
        raise RunFailed(str(exc.detail)[:300]) from None
    kind = AssistantStep.KIND_ROUTE if key == 'route' else AssistantStep.KIND_MODEL
    if 'plan' in data:
        output = data['plan']
    elif 'tool_calls' in data:
        output = {'text': data.get('text', ''), 'tool_calls': data.get('tool_calls') or [],
                  'native': data.get('native'), 'links_removed': data.get('links_removed', 0)}
    else:
        output = {'text': data.get('text', '')}
    cost = Decimal(str(data.get('cost_usd', 0))).quantize(Decimal('0.000001'))
    step = _append(run, key, kind, model=str(data.get('model', ''))[:60],
                   prompt_version=str(data.get('prompt_version', ''))[:20], output=output,
                   input_tokens=int(data.get('input_tokens', 0)), output_tokens=int(data.get('output_tokens', 0)),
                   cost_usd=cost, duration_ms=int((time.monotonic() - started) * 1000))
    AssistantRun.objects.filter(pk=run.pk).update(
        step_count=F('step_count') + 1, input_tokens=F('input_tokens') + step.input_tokens,
        output_tokens=F('output_tokens') + step.output_tokens, cost_usd=F('cost_usd') + cost)
    run.refresh_from_db()
    events.push(run, 'assistant.step', step=_summary(step))
    return step


def _context(run, call_id=''):
    last = run.steps.filter(kind=AssistantStep.KIND_MODEL).order_by('-index').first() or _step(run, 'route')
    return tools.Context(user=run.owner, run=run, call_id=call_id, model=last.model if last else '',
                         prompt_version=last.prompt_version if last else '')


def _tool_call(run, call_id, name, arguments):
    """Execute a read tool once per call id; a retry returns the recorded result."""
    key = f'tool:{call_id}'
    existing = _step(run, key)
    if existing:
        return existing
    started = time.monotonic()
    outcome = tools.execute(name, arguments, _context(run, call_id))
    step = _append(run, key, AssistantStep.KIND_TOOL, tool_name=str(name)[:40],
                   tool_args=arguments if isinstance(arguments, dict) else {}, tool_result=outcome.content,
                   is_error=outcome.is_error, output={'citations': outcome.citations},
                   duration_ms=int((time.monotonic() - started) * 1000))
    events.push(run, 'assistant.step', step=_summary(step))
    return step


DECISION_TEXT = {
    Proposal.STATUS_APPROVED: 'The member approved this. Done: {result}.',
    Proposal.STATUS_REJECTED: 'The member rejected this proposal. Nothing was done. Do not propose it again.',
    Proposal.STATUS_EXPIRED: 'The proposal expired before the member approved it. Nothing was done.',
    Proposal.STATUS_FAILED: 'This could not be done when the member approved it: {error}',
}


def record_decision(proposal):
    """Give the model the outcome of a proposal, as the result of the tool call that made it."""
    if proposal.run_id is None or proposal.status == Proposal.STATUS_PENDING:
        return None
    text = DECISION_TEXT[proposal.status].format(result=json.dumps(proposal.result), error=proposal.error)
    return _append(proposal.run, f'tool:{proposal.call_id}', AssistantStep.KIND_TOOL, tool_name=proposal.tool,
                   tool_args=proposal.arguments, tool_result=text,
                   is_error=proposal.status in (Proposal.STATUS_EXPIRED, Proposal.STATUS_FAILED),
                   output={'proposal_id': proposal.id, 'decision': proposal.status})


def expire(proposal):
    if Proposal.objects.filter(pk=proposal.pk, status=Proposal.STATUS_PENDING).update(
            status=Proposal.STATUS_EXPIRED, decided_at=timezone.now()):
        proposal.refresh_from_db()
        record_decision(proposal)


def _write_call(run, call_id, name, arguments):
    """A write tool call: create (or find) its proposal. Returns True while it waits for the member."""
    if _step(run, f'tool:{call_id}'):
        return False
    proposal = Proposal.objects.filter(run=run, call_id=call_id).first()
    if proposal is None:
        outcome = tools.execute(name, arguments, _context(run, call_id))
        if outcome.proposal is None:  # invalid or not allowed: the model reads why
            _append(run, f'tool:{call_id}', AssistantStep.KIND_TOOL, tool_name=str(name)[:40],
                    tool_args=arguments if isinstance(arguments, dict) else {}, tool_result=outcome.content,
                    is_error=True)
            return False
        proposal = outcome.proposal
        events.push(run, 'assistant.proposal', proposal_id=proposal.id)
    if proposal.status == Proposal.STATUS_PENDING and proposal.is_expired:
        expire(proposal)
        proposal.refresh_from_db()
    if proposal.status == Proposal.STATUS_PENDING:
        return True
    record_decision(proposal)
    return False


# ── Conversation ─────────────────────────────────────────────────────────────

def _previous(run):
    chain, prev = [], run.follow_up_of
    while prev is not None and len(chain) < MAX_FOLLOW_UPS:
        if prev.owner_id == run.owner_id and prev.status == AssistantRun.STATUS_DONE:
            chain.append({'request': prev.request_text[:2000], 'answer': prev.answer[:4000]})
        prev = prev.follow_up_of
    return list(reversed(chain))


def _first_turn(run):
    context = [{'label': 'earlier_turn', 'content': f"Member: {p['request']}\nAssistant: {p['answer']}"}
               for p in _previous(run)]
    return {'role': 'user', 'text': f'Member: @{run.owner.username}\nRequest: {run.request_text}',
            'context': context}


def _model_steps(run):
    steps = [s for s in run.steps.filter(kind=AssistantStep.KIND_MODEL) if s.key.startswith('model:')]
    return sorted(steps, key=lambda s: int(s.key.split(':')[1]))


def build_turns(run):
    """The conversation so far, rebuilt from recorded steps exactly as the model saw it."""
    turns = [_first_turn(run)]
    results = {s.key: s for s in run.steps.filter(kind=AssistantStep.KIND_TOOL)}
    for step in _model_steps(run):
        out = step.output
        calls = out.get('tool_calls') or []
        turns.append({'role': 'assistant', 'text': out.get('text', ''), 'tool_calls': calls,
                      'native': out.get('native')})
        if calls:
            turns.append({'role': 'tool', 'results': [
                {'call_id': c['id'], 'name': c['name'], 'content': results[f"tool:{c['id']}"].tool_result,
                 'is_error': results[f"tool:{c['id']}"].is_error} for c in calls]})
    return turns


# ── Finishing ────────────────────────────────────────────────────────────────

def strip_links(text, allowed_source):
    """Links in an answer survive only if the member typed them. Defence in depth over the AI service."""
    allowed = set(_URL_RE.findall(allowed_source or ''))
    return _URL_RE.sub(lambda m: m.group(0) if m.group(0) in allowed else '[link removed]', text or '')


def _citations(run, text):
    known = {}
    for s in run.steps.filter(kind=AssistantStep.KIND_TOOL):
        for c in (s.output or {}).get('citations', []):
            known.setdefault(c['id'], c)
    cited = dict.fromkeys(f'{k}:{i}' for k, i in _CITE_RE.findall(text or ''))
    return [known[c] for c in cited if c in known]


def finish(run, text):
    text = strip_links(text, run.request_text).strip() or "I couldn't come up with an answer."
    run.answer = text[:8000]
    run.citations = _citations(run, text)
    run.status = AssistantRun.STATUS_DONE
    run.locked_until = None
    run.save(update_fields=['answer', 'citations', 'status', 'locked_until', 'updated_at'])
    events.push(run, 'assistant.done')


def fail(run, reason):
    run.status = AssistantRun.STATUS_FAILED
    run.error = str(reason)[:300]
    run.locked_until = None
    run.save(update_fields=['status', 'error', 'locked_until', 'updated_at'])
    events.push(run, 'assistant.failed')


def _await(run, interim=''):
    """
    Pause for the member. Returns False if every proposal was decided in the
    meantime, so the caller carries on instead. The run row is locked, as it is
    when a proposal is decided, so a decision can't slip in between the check
    and the pause and leave the run waiting for nothing.
    """
    with transaction.atomic():
        AssistantRun.objects.select_for_update().filter(pk=run.pk).first()
        if not run.proposals.filter(status=Proposal.STATUS_PENDING).exists():
            return False
        run.status = AssistantRun.STATUS_AWAITING
        if interim:
            run.answer = strip_links(interim, run.request_text)[:8000]
        run.locked_until = None
        run.save(update_fields=['status', 'answer', 'locked_until', 'updated_at'])
    events.push(run, 'assistant.awaiting_approval')
    return True


# ── Paths ────────────────────────────────────────────────────────────────────

def _route(run):
    step = _model_call(run, 'route', '/v1/assistant/route',
                       {'request': run.request_text[:2000], 'previous': _previous(run)})
    path = step.output.get('path')
    if path not in dict(AssistantRun.PATH_CHOICES):
        path = 'agent'
    if run.path != path:
        run.path = path
        run.save(update_fields=['path', 'updated_at'])
        logger.info('Assistant run %s took the %s path', run.id, path)
    return step.output


def _search(run, plan):
    query = (plan.get('query') or run.request_text)[:200]
    if len(query) < 2:
        query = run.request_text[:200]
    found = _tool_call(run, 'wf-search', 'search_content', {'query': query})
    if found.is_error or not (found.output or {}).get('citations'):
        return finish(run, "I couldn't find anything you can see about that.")
    step = _model_call(run, 'model:0', '/v1/assistant/step', {
        'task': 'answer', 'tools': [],
        'turns': [{**_first_turn(run), 'context': _first_turn(run)['context'] + [
            {'label': 'search_results', 'content': found.tool_result}]}]})
    finish(run, step.output.get('text', ''))


def _match_rooms(user, hint):
    from chats.views import rooms_for
    hint = (hint or '').strip().lower()
    rooms = list(rooms_for(user)[:100])
    if not hint:
        return rooms
    matches = []
    for r in rooms:
        names = [r.name or ''] + [f'{m.user.username} {m.user.first_name} {m.user.last_name}'
                                  for m in r.chatmember_set.all() if m.user_id != user.id]
        if any(hint in n.lower() for n in names):
            matches.append(r)
    return matches


def _room_label(room, user):
    return room.name or ', '.join(m.user.username for m in room.chatmember_set.all() if m.user_id != user.id)


def _summarise(run, plan):
    rooms = _match_rooms(run.owner, plan.get('room'))
    if len(rooms) != 1:
        if not rooms:
            return finish(run, "I couldn't find a chat like that. Which chat do you mean?")
        names = '; '.join(_room_label(r, run.owner) for r in rooms[:5])
        return finish(run, f'Which chat do you mean? I found: {names}.')
    found = _tool_call(run, 'wf-summarise', 'summarise_thread', {'room_id': rooms[0].id})
    if found.is_error:
        return finish(run, found.tool_result)
    s = json.loads(found.tool_result)
    lines = [s.get('tldr') or s.get('summary') or '']
    lines += [f"- {t['title']}: {t['summary']}" for t in s.get('topics', [])]
    if s.get('decisions'):
        lines.append('Decided: ' + '; '.join(s['decisions']))
    if s.get('questions_for_you'):
        lines.append('Waiting on you: ' + '; '.join(s['questions_for_you']))
    finish(run, '\n'.join(line for line in lines if line))


def _match_group(user, hint):
    from groups.models import Group
    qs = Group.objects.filter(memberships__user=user)
    exact = qs.filter(name__iexact=hint)
    return list(exact[:2]) or list(qs.filter(name__icontains=hint)[:5])


def _match_person(user, hint):
    from django.contrib.auth import get_user_model

    from core import visibility
    User = get_user_model()
    hint = hint.strip().lstrip('@')
    blocked = visibility.blocked_ids(user)
    exact = User.objects.filter(username__iexact=hint, is_active=True).exclude(id__in=blocked).exclude(id=user.id)
    if exact.exists():
        return list(exact[:1])
    friends = User.objects.filter(id__in=visibility.friend_ids(user), is_active=True).exclude(id__in=blocked)
    return list(friends.filter(Q(username__icontains=hint) | Q(first_name__icontains=hint)
                               | Q(last_name__icontains=hint))[:5])


def _draft(run, plan):
    kind = 'post' if run.path == 'draft_post' else 'message'
    call_id = f'wf-{kind}'
    if _step(run, f'tool:{call_id}') or Proposal.objects.filter(run=run, call_id=call_id).exists():
        return _after_proposal(run, call_id)
    args, audience = {}, 'their timeline'
    if kind == 'post' and plan.get('group'):
        groups = _match_group(run.owner, plan['group'])
        if len(groups) != 1:
            return finish(run, f"You're not in a group called \"{plan['group']}\"." if not groups else
                          'Which group? ' + '; '.join(g.name for g in groups))
        args['group_id'], audience = groups[0].id, groups[0].name
    if kind == 'message':
        people = _match_person(run.owner, plan.get('recipient') or '')
        if len(people) != 1:
            return finish(run, "I couldn't tell who to message. Who should it go to?" if not people else
                          'Who do you mean? ' + ', '.join(f'@{p.username}' for p in people))
        args['to_user_id'], audience = people[0].id, f'@{people[0].username}'
    step = _model_call(run, 'draft', '/v1/assistant/draft', {
        'kind': kind, 'request': run.request_text[:2000], 'viewer': run.owner.username, 'audience': audience,
        'previous': _previous(run)})
    text = (step.output.get('text') or '').strip()
    if not text:
        return finish(run, "I couldn't write that. Try saying a bit more about what you want.")
    _write_call(run, call_id, 'create_post' if kind == 'post' else 'send_message', {**args, 'text': text})
    return _after_proposal(run, call_id)


def _after_proposal(run, call_id):
    result = _step(run, f'tool:{call_id}')
    if result is None:
        proposal = Proposal.objects.filter(run=run, call_id=call_id).first()
        if proposal is not None and _write_call(run, call_id, proposal.tool, proposal.arguments):
            verb = 'post' if proposal.tool == 'create_post' else 'send'
            noun = 'post' if verb == 'post' else 'message'
            if _await(run, f"Here's a draft {noun}. Check it and approve it to {verb} it."):
                return None
            proposal.refresh_from_db()
            record_decision(proposal)
        result = _step(run, f'tool:{call_id}')
    decision = (result.output or {}).get('decision') if result else None
    if decision == Proposal.STATUS_APPROVED:
        return finish(run, 'Done. It has been posted.' if call_id == 'wf-post' else 'Done. Your message was sent.')
    if decision == Proposal.STATUS_REJECTED:
        return finish(run, "Okay, I won't do that.")
    return finish(run, result.tool_result if result else "I couldn't prepare that.")


def _agent(run):
    specs = tools.specs()
    while True:
        model_steps = _model_steps(run)
        last = model_steps[-1] if model_steps else None
        if last is not None:
            calls = last.output.get('tool_calls') or []
            if not calls:
                return finish(run, last.output.get('text', ''))
            waiting = False
            for i, call in enumerate(calls):
                call_id, name, arguments = call['id'], call['name'], call.get('arguments') or {}
                if i >= MAX_CALLS_PER_STEP:
                    if not _step(run, f'tool:{call_id}'):
                        _append(run, f'tool:{call_id}', AssistantStep.KIND_TOOL, tool_name=str(name)[:40],
                                tool_result='Skipped: too many tool calls in one step.', is_error=True)
                    continue
                tool = tools.TOOLS.get(name)
                if tool is not None and tool.writes:
                    waiting = _write_call(run, call_id, name, arguments) or waiting
                else:
                    _tool_call(run, call_id, name, arguments)
            if waiting and _await(run, last.output.get('text', '') or 'I need your approval before I continue.'):
                return None
            if waiting:
                continue  # decided while we were working: pick the results up on the next pass
        if len(model_steps) >= MAX_AGENT_STEPS:
            return finish(run, f"I stopped after {MAX_AGENT_STEPS} steps without finishing. "
                               'Try asking for something more specific.')
        try:
            _model_call(run, f'model:{len(model_steps)}', '/v1/assistant/step',
                        {'task': 'agent', 'turns': build_turns(run), 'tools': specs})
        except BudgetReached:
            return finish(run, 'I stopped because this request used up its budget. Try something more specific.')


def advance(run):
    """Move a run forward until it finishes, fails or waits for the member. Safe to call repeatedly."""
    if run.status in (AssistantRun.STATUS_DONE, AssistantRun.STATUS_FAILED):
        return run
    try:
        plan = _route(run)
        if run.path == 'search':
            _search(run, plan)
        elif run.path == 'summarise':
            _summarise(run, plan)
        elif run.path in ('draft_post', 'draft_message'):
            _draft(run, plan)
        else:
            _agent(run)
    except BudgetReached:
        finish(run, 'I stopped because this request used up its budget.')
    except RunFailed as exc:
        fail(run, exc)
    return run


def claim(run_id):
    """Take the run for this worker, unless another worker holds it or it isn't runnable."""
    now = timezone.now()
    return AssistantRun.objects.filter(
        pk=run_id, status__in=[AssistantRun.STATUS_QUEUED, AssistantRun.STATUS_RUNNING],
    ).filter(Q(locked_until__isnull=True) | Q(locked_until__lt=now)).update(
        status=AssistantRun.STATUS_RUNNING, locked_until=now + LEASE) == 1


def release(run_id):
    AssistantRun.objects.filter(pk=run_id).update(locked_until=None)


def resume(run):
    """Queue an awaiting run again once none of its proposals are still pending."""
    if run.status != AssistantRun.STATUS_AWAITING:
        return False
    if run.proposals.filter(status=Proposal.STATUS_PENDING).exists():
        return False
    if not AssistantRun.objects.filter(pk=run.pk, status=AssistantRun.STATUS_AWAITING).update(
            status=AssistantRun.STATUS_QUEUED):
        return False
    from .tasks import dispatch
    transaction.on_commit(lambda: dispatch(run.id))
    return True
