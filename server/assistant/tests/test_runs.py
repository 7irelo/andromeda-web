"""Runs: routing, fixed workflows, the agent loop, durability and approvals."""
import asyncio
import datetime as dt

import pytest
from django.utils import timezone

from assistant import runner, tools
from assistant.models import AIWriteAudit, AssistantRun, AssistantStep, Proposal
from chats.models import Message
from core import ai_client
from core.test_security import client_for, make_user
from groups.models import Group, GroupMember
from posts.models import Post

from .conftest import call

pytestmark = pytest.mark.django_db


def test_search_path_answers_with_verified_citations(fake_ai, ask, thandi, sipho):
    post = Post.objects.create(author=sipho, content='Parkrun at Delta Park every Saturday 8am')
    fake = fake_ai(route={'path': 'search', 'query': 'parkrun'},
                   steps=[{'text': f'Saturdays at 8am [posts:{post.id}] [posts:99999]'}])
    run = ask(thandi, 'when is parkrun?')
    run.refresh_from_db()
    assert run.status == 'done' and run.path == 'search'
    assert fake.paths() == ['/v1/assistant/route', '/v1/assistant/step']
    answer = fake.payloads('/v1/assistant/step')[0]
    assert answer['task'] == 'answer' and answer['tools'] == []
    assert 'Delta Park' in answer['turns'][0]['context'][0]['content']
    assert [c['id'] for c in run.citations] == [f'posts:{post.id}']  # the invented id is dropped
    assert run.citations[0]['url'] == f'/posts/{post.id}'
    assert run.step_count == 2 and run.total_tokens == 2200


def test_search_with_nothing_visible_skips_the_answer_model(fake_ai, ask, thandi, sipho):
    Post.objects.create(author=sipho, content='parkrun secret', privacy=Post.PRIVACY_PRIVATE)
    fake = fake_ai(route={'path': 'search', 'query': 'parkrun'})
    run = ask(thandi, 'parkrun?')
    run.refresh_from_db()
    assert run.status == 'done' and "couldn't find" in run.answer
    assert '/v1/assistant/step' not in fake.paths()


def test_draft_post_becomes_a_proposal_and_posts_only_after_approval(fake_ai, ask, decide, thandi):
    group = Group.objects.create(name='Braai Club', created_by=thandi)
    GroupMember.objects.create(group=group, user=thandi, role='admin')
    fake_ai(route={'path': 'draft_post', 'group': 'braai'}, draft='Braai at mine on Saturday!')
    run = ask(thandi, 'write a post for the braai club inviting everyone on saturday')
    run.refresh_from_db()
    assert run.status == 'awaiting_approval' and run.path == 'draft_post'
    proposal = run.proposals.get()
    assert proposal.tool == 'create_post' and proposal.status == 'pending'
    assert proposal.preview['text'] == 'Braai at mine on Saturday!' and proposal.preview['group']['id'] == group.id
    assert not Post.objects.exists()

    r = decide(thandi, proposal)
    assert r.status_code == 200 and r.json()['status'] == 'approved'
    post = Post.objects.get()
    assert post.author == thandi and post.group == group and post.content == 'Braai at mine on Saturday!'
    audit = AIWriteAudit.objects.get()
    assert (audit.user, audit.approved_by, audit.object_type, audit.object_id) == (thandi, thandi, 'post', post.id)
    assert audit.model == 'claude-sonnet-5-5' and audit.prompt_version == 'abc123def456'
    assert audit.tool_calls  # the trace that led here
    run.refresh_from_db()
    assert run.status == 'done' and 'posted' in run.answer


def test_draft_message_rejected_sends_nothing(fake_ai, ask, decide, thandi, sipho):
    fake_ai(route={'path': 'draft_message', 'recipient': 'sipho'}, draft="Running 10 minutes late!")
    run = ask(thandi, "tell sipho I'm running late")
    proposal = Proposal.objects.get(run=run)
    assert proposal.preview['to'][0]['username'] == 'sipho'
    assert decide(thandi, proposal, 'reject').json()['status'] == 'rejected'
    run.refresh_from_db()
    assert run.status == 'done' and not Message.objects.exists() and not AIWriteAudit.objects.exists()


def test_approved_message_is_sent_in_a_dm(fake_ai, ask, decide, thandi, sipho):
    fake_ai(route={'path': 'draft_message', 'recipient': 'Sipho'}, draft='See you at 6')
    run = ask(thandi, 'message sipho see you at 6')
    decide(thandi, Proposal.objects.get(run=run))
    msg = Message.objects.get()
    assert msg.sender == thandi and set(msg.room.members.all()) == {thandi, sipho}


def test_summarise_path_reuses_catch_up(fake_ai, ask, thandi, sipho):
    from chats.tests.helpers import make_room
    room = make_room(thandi, sipho, name='Family')
    for text in ('braai saturday?', 'yes at 2', 'bring wood'):
        Message.objects.create(room=room, sender=sipho, content=text)
    fake = fake_ai(route={'path': 'summarise', 'room': 'family'},
                   catchup={'tldr': 'Braai Saturday at 2.', 'topics': [{'title': 'Braai', 'summary': 'At 2'}],
                            'decisions': [{'text': 'Bring wood'}], 'questions_for_you': []})
    run = ask(thandi, 'catch me up on the family chat')
    run.refresh_from_db()
    assert run.status == 'done' and 'Braai Saturday at 2.' in run.answer and 'Bring wood' in run.answer
    catchup = fake.payloads('/v1/catchup')[0]
    assert [m['text'] for m in catchup['messages']] == ['braai saturday?', 'yes at 2', 'bring wood']


def test_agent_loop_feeds_tool_results_back_and_replays_native_content(fake_ai, ask, thandi):
    group = Group.objects.create(name='Runners', created_by=thandi)
    GroupMember.objects.create(group=group, user=thandi)
    fake = fake_ai(steps=[{'calls': [call('list_my_groups')]}, {'text': 'You are in Runners.'}])
    run = ask(thandi, 'which groups am I in and what is new in them?')
    run.refresh_from_db()
    assert run.status == 'done' and run.answer == 'You are in Runners.' and run.path == 'agent'
    second = fake.payloads('/v1/assistant/step')[1]
    assert [t['role'] for t in second['turns']] == ['user', 'assistant', 'tool']
    assert second['turns'][1]['native']['content'][0]['signature'].startswith('sig-')
    assert 'Runners' in second['turns'][2]['results'][0]['content']
    assert {t['name'] for t in second['tools']} == set(tools.TOOLS)
    kinds = list(run.steps.values_list('kind', 'tool_name'))
    assert kinds == [('route', ''), ('model', ''), ('tool', 'list_my_groups'), ('model', '')]


def test_run_resumes_after_a_crash_without_repeating_tool_calls(fake_ai, thandi, monkeypatch):
    executed = []
    original = tools.TOOLS['list_my_groups']
    monkeypatch.setitem(tools.TOOLS, 'list_my_groups', tools.Tool(
        original.name, original.description, original.args, original.schema,
        lambda ctx, args: executed.append(1) or original.run(ctx, args)))
    fake = fake_ai(steps=[{'calls': [call('list_my_groups')]}, {'text': 'Done.'}])
    run = AssistantRun.objects.create(owner=thandi, request_text='my groups?', status='running')
    # First attempt: the route and the first step succeed, the tool runs, then the provider goes down.
    real_call = fake.__call__
    count = {'step': 0}

    def flaky(path, payload, user_id):
        if path == '/v1/assistant/step':
            count['step'] += 1
            if count['step'] == 2:
                raise ai_client.AIUnavailable('down')
        return real_call(path, payload, user_id)

    monkeypatch.setattr(ai_client, 'call', flaky)
    with pytest.raises(ai_client.AIUnavailable):
        runner.advance(run)
    assert executed == [1] and run.steps.count() == 3
    # Retry: picks up after the recorded tool result.
    runner.advance(run)
    run.refresh_from_db()
    assert run.status == 'done' and run.answer == 'Done.' and executed == [1]
    assert [s.key for s in run.steps.order_by('index')] == ['route', 'model:0', 'tool:toolu_1', 'model:1']


def test_outage_is_retried_then_fails_cleanly(fake_ai, thandi):
    from celery.exceptions import Retry

    from assistant.tasks import execute_run
    fake = fake_ai()
    fake.fail_on.add('/v1/assistant/route')
    run = AssistantRun.objects.create(owner=thandi, request_text='anything')
    with pytest.raises(Retry):
        execute_run.apply(args=[run.id], throw=True)
    run.refresh_from_db()
    assert run.status == 'running' and run.locked_until is None  # free for the retry to claim
    execute_run.apply(args=[run.id], retries=3)
    run.refresh_from_db()
    assert run.status == 'failed' and 'unavailable' in run.error


def test_lost_runs_are_requeued(fake_ai, thandi, monkeypatch):
    from assistant import tasks
    fake_ai(steps=[{'text': 'ok'}])
    run = AssistantRun.objects.create(owner=thandi, request_text='anything')
    AssistantRun.objects.filter(pk=run.pk).update(updated_at=timezone.now() - dt.timedelta(hours=1))
    assert tasks.requeue_stuck_runs() == 1
    run.refresh_from_db()
    assert run.status == 'done' and tasks.requeue_stuck_runs() == 0


def test_step_limit_stops_the_loop(fake_ai, ask, thandi):
    fake_ai(steps=[{'calls': [call('list_my_groups')]}] * 20)
    run = ask(thandi, 'loop forever')
    run.refresh_from_db()
    assert run.status == 'done' and 'stopped after 8 steps' in run.answer
    assert run.steps.filter(kind='model').count() == 8


def test_cost_budget_stops_the_loop(fake_ai, ask, thandi):
    fake_ai(steps=[{'calls': [call('list_my_groups')]}] * 20, cost=0.3)
    run = ask(thandi, 'expensive')
    run.refresh_from_db()
    assert run.status == 'done' and 'budget' in run.answer and run.step_count == 2


def test_model_refusal_fails_the_run(fake_ai, ask, thandi, monkeypatch):
    def refuse(path, payload, user_id):
        raise ai_client.AIRejected(422, 'The model declined this request')
    fake_ai()
    monkeypatch.setattr(ai_client, 'call', refuse)
    run = ask(thandi, 'something')
    run.refresh_from_db()
    assert run.status == 'failed' and run.error == 'The model declined this request'


def test_follow_ups_carry_earlier_turns_as_untrusted_context(fake_ai, ask, thandi):
    fake = fake_ai(steps=[{'text': 'First answer.'}, {'text': 'Second answer.'}])
    first = ask(thandi, 'first question')
    ask(thandi, 'and then?', follow_up_of=first.id)
    turn = fake.payloads('/v1/assistant/step')[1]['turns'][0]
    assert turn['context'][0]['label'] == 'earlier_turn' and 'First answer.' in turn['context'][0]['content']
    assert fake.payloads('/v1/assistant/route')[1]['previous'][0]['answer'] == 'First answer.'


def test_runs_are_private_and_gated(fake_ai, ask, thandi, sipho, settings):
    fake_ai(steps=[{'text': 'ok'}])
    run = ask(thandi, 'hello there')
    assert client_for(sipho).get(f'/api/assistant/runs/{run.id}/').status_code == 404
    assert client_for(sipho).get('/api/assistant/runs/').json() == []
    body = client_for(thandi).get(f'/api/assistant/runs/{run.id}/').json()
    assert body['answer'] == 'ok' and 'native' not in str(body) and 'tool_result' not in body['steps'][0]
    hijack = client_for(sipho).post('/api/assistant/runs/', {'request': 'hi', 'follow_up_of': run.id}, format='json')
    assert hijack.status_code == 400
    opted = make_user('optout', ai_opt_out=True)
    assert client_for(opted).post('/api/assistant/runs/', {'request': 'hi'}, format='json').status_code == 403


def test_assistant_unavailable_without_ai_service(thandi):
    r = client_for(thandi).post('/api/assistant/runs/', {'request': 'hello'}, format='json')
    assert r.status_code == 503


def test_proposals_are_single_use_and_expire(fake_ai, ask, decide, thandi):
    fake_ai(route={'path': 'draft_post'}, draft='Hello world')
    run = ask(thandi, 'post hello world')
    proposal = run.proposals.get()
    assert decide(thandi, proposal).status_code == 200
    assert decide(thandi, proposal).status_code == 409
    assert Post.objects.count() == 1

    run2 = ask(thandi, 'post hello again')
    stale = run2.proposals.get()
    Proposal.objects.filter(pk=stale.pk).update(expires_at=timezone.now() - dt.timedelta(seconds=1))
    assert decide(thandi, stale).status_code == 410
    run2.refresh_from_db()
    assert run2.status == 'done' and Post.objects.count() == 1


def test_expiry_task_finishes_waiting_runs(fake_ai, ask, thandi, django_capture_on_commit_callbacks):
    from assistant.tasks import expire_proposals
    fake_ai(route={'path': 'draft_post'}, draft='Hello world')
    run = ask(thandi, 'post hello world')
    Proposal.objects.filter(run=run).update(expires_at=timezone.now() - dt.timedelta(minutes=1))
    with django_capture_on_commit_callbacks(execute=True):
        assert expire_proposals() == 1
    run.refresh_from_db()
    assert run.status == 'done' and run.proposals.get().status == 'expired' and not Post.objects.exists()


def test_approval_revalidates_permissions(fake_ai, ask, decide, thandi):
    group = Group.objects.create(name='Braai Club', created_by=thandi)
    GroupMember.objects.create(group=group, user=thandi)
    fake_ai(route={'path': 'draft_post', 'group': 'Braai Club'}, draft='See you there')
    run = ask(thandi, 'post in braai club')
    GroupMember.objects.filter(group=group, user=thandi).delete()  # removed from the group meanwhile
    r = decide(thandi, run.proposals.get())
    assert r.json()['status'] == 'failed' and 'Join this group' in r.json()['error']
    assert not Post.objects.exists() and not AIWriteAudit.objects.exists()


def test_steps_and_audit_rows_are_append_only(fake_ai, ask, thandi):
    fake_ai(steps=[{'text': 'ok'}])
    run = ask(thandi, 'hello there')
    step = run.steps.first()
    step.tool_result = 'tampered'
    with pytest.raises(ValueError):
        step.save()
    assert AssistantStep.objects.filter(tool_result='tampered').count() == 0


def test_progress_events_reach_only_whitelisted_keys():
    from notifications.consumers import NotificationConsumer
    consumer = NotificationConsumer()
    sent = []

    async def capture(text_data=None, **kwargs):
        sent.append(text_data)
    consumer.send = capture
    asyncio.run(consumer.assistant_event({'type': 'assistant_event', 'payload': {
        'event': 'assistant.step', 'run_id': 4, 'status': 'running', 'secret': 'x',
        'step': {'index': 1, 'kind': 'tool', 'tool': 'get_post', 'tool_result': 'private'}}}))
    asyncio.run(consumer.assistant_event({'type': 'assistant_event', 'payload': {'run_id': 'nope'}}))
    assert len(sent) == 1
    assert 'secret' not in sent[0] and 'private' not in sent[0] and '"type": "assistant.event"' in sent[0]


def test_events_are_pushed_to_the_owners_socket_group(fake_ai, ask, thandi, monkeypatch):
    pushed = []
    monkeypatch.setattr('assistant.events.push', lambda run, event, **extra: pushed.append((run.owner_id, event)))
    fake_ai(steps=[{'calls': [call('list_my_groups')]}, {'text': 'ok'}])
    ask(thandi, 'groups?')
    assert {o for o, _ in pushed} == {thandi.id}
    assert [e for _, e in pushed][-1] == 'assistant.done' and ('assistant.step' in [e for _, e in pushed])
