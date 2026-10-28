"""The MCP endpoint and personal access tokens."""
import base64
import datetime as dt

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from assistant.auth import MCPRateThrottle
from assistant.models import AIWriteAudit, PersonalAccessToken, Proposal
from core.test_security import PASSWORD, client_for
from groups.models import Group, GroupMember
from posts.models import Post

pytestmark = pytest.mark.django_db
MODERN = '2026-07-28'


def issue(user, scopes=('read',), days=30):
    r = client_for(user).post('/api/assistant/tokens/', {'name': 'Laptop', 'scopes': list(scopes),
                                                          'expires_in_days': days, 'password': PASSWORD},
                              format='json')
    assert r.status_code == 201, r.content
    return r.json()['token']


def rpc(token, method, params=None, msg_id=1, headers=None, version='2025-11-25'):
    c = APIClient()
    hdrs = {'HTTP_AUTHORIZATION': f'Bearer {token}'} if token else {}
    if version:
        hdrs['HTTP_MCP_PROTOCOL_VERSION'] = version
    hdrs.update(headers or {})
    body = {'jsonrpc': '2.0', 'method': method, 'params': params or {}}
    if msg_id is not None:
        body['id'] = msg_id
    return c.post('/api/mcp/', body, format='json', **hdrs)


def test_tokens_are_shown_once_and_stored_hashed(thandi):
    raw = issue(thandi, days=90)
    row = PersonalAccessToken.objects.get()
    assert raw.startswith('andp_') and row.token_hash == PersonalAccessToken.hash(raw) and raw not in str(
        PersonalAccessToken.objects.values().get())
    listed = client_for(thandi).get('/api/assistant/tokens/').json()
    assert listed[0]['prefix'] == raw[:12] and 'token' not in listed[0] and 'token_hash' not in listed[0]
    assert (row.expires_at - timezone.now()).days >= 89


@pytest.mark.parametrize('bad', [{'password': 'wrong'}, {'expires_in_days': 91}, {'scopes': ['admin']},
                                 {'scopes': []}])
def test_token_creation_rules(thandi, bad):
    body = {'name': 'x', 'scopes': ['read'], 'expires_in_days': 30, 'password': PASSWORD, **bad}
    assert client_for(thandi).post('/api/assistant/tokens/', body, format='json').status_code == 400
    assert not PersonalAccessToken.objects.exists()


def test_initialize_and_tool_listing_follow_scopes(thandi):
    read = issue(thandi)
    r = rpc(read, 'initialize', {'protocolVersion': '2025-11-25', 'capabilities': {},
                                 'clientInfo': {'name': 'test', 'version': '1'}}, version=None)
    assert r.json()['result']['protocolVersion'] == '2025-11-25' and 'tools' in r.json()['result']['capabilities']
    assert rpc(read, 'notifications/initialized', msg_id=None).status_code == 202
    names = {t['name'] for t in rpc(read, 'tools/list').json()['result']['tools']}
    assert 'search_content' in names and 'create_post' not in names and 'send_message' not in names
    propose = issue(thandi, ('read', 'propose'))
    tools = {t['name']: t for t in rpc(propose, 'tools/list').json()['result']['tools']}
    assert tools['create_post']['annotations']['readOnlyHint'] is False
    assert 'approves' in tools['create_post']['description']


def test_read_tool_call_runs_as_the_token_owner(thandi, sipho):
    group = Group.objects.create(name='Runners', created_by=thandi)
    GroupMember.objects.create(group=group, user=thandi)
    r = rpc(issue(thandi), 'tools/call', {'name': 'list_my_groups', 'arguments': {}})
    result = r.json()['result']
    assert result['isError'] is False and 'Runners' in result['content'][0]['text']
    r = rpc(issue(sipho), 'tools/call', {'name': 'list_my_groups', 'arguments': {}})
    assert 'Runners' not in r.json()['result']['content'][0]['text']


def test_scopes_are_enforced_per_tool(thandi):
    r = rpc(issue(thandi), 'tools/call', {'name': 'create_post', 'arguments': {'text': 'hi'}})
    assert r.json()['result']['isError'] is True and 'propose' in r.json()['result']['content'][0]['text']
    assert not Proposal.objects.exists()


def test_mcp_writes_are_proposals_approved_in_the_app(thandi, django_capture_on_commit_callbacks, monkeypatch):
    from core import ai_client
    monkeypatch.setattr(ai_client, 'enabled', lambda: False)  # moderation is skipped without the AI service
    r = rpc(issue(thandi, ('read', 'propose')), 'tools/call',
            {'name': 'create_post', 'arguments': {'text': 'From my MCP client'}})
    assert r.json()['result']['isError'] is False and 'approve' in r.json()['result']['content'][0]['text']
    proposal = Proposal.objects.get()
    assert proposal.source == 'mcp' and proposal.run is None and not Post.objects.exists()
    assert client_for(thandi).get('/api/assistant/proposals/?status=pending').json()[0]['id'] == proposal.id
    with django_capture_on_commit_callbacks(execute=True):
        r = client_for(thandi).post(f'/api/assistant/proposals/{proposal.id}/approve/')
    assert r.json()['status'] == 'approved' and Post.objects.get().author == thandi
    audit = AIWriteAudit.objects.get()
    assert audit.source == 'mcp' and audit.model == 'mcp:Laptop' and audit.approved_by == thandi


def test_mcp_cannot_approve_proposals(thandi):
    rpc(issue(thandi, ('read', 'propose')), 'tools/call', {'name': 'create_post', 'arguments': {'text': 'x'}})
    proposal = Proposal.objects.get()
    c = APIClient()
    raw = issue(thandi, ('read', 'propose'))
    r = c.post(f'/api/assistant/proposals/{proposal.id}/approve/', HTTP_AUTHORIZATION=f'Bearer {raw}')
    assert r.status_code == 401
    assert c.get('/api/assistant/tokens/', HTTP_AUTHORIZATION=f'Bearer {raw}').status_code == 401
    assert c.get('/api/posts/', HTTP_AUTHORIZATION=f'Bearer {raw}').status_code == 401


def test_bad_tokens_are_rejected(thandi):
    r = rpc(None, 'tools/list')
    assert r.status_code == 401 and r.headers['WWW-Authenticate'].startswith('Bearer')
    assert rpc('andp_not-a-real-token', 'tools/list').status_code == 401
    raw = issue(thandi)
    PersonalAccessToken.objects.update(expires_at=timezone.now() - dt.timedelta(seconds=1))
    assert rpc(raw, 'tools/list').status_code == 401
    raw = issue(thandi)
    token = PersonalAccessToken.objects.get(prefix=raw[:12])
    assert client_for(thandi).delete(f'/api/assistant/tokens/{token.id}/').status_code == 204
    assert rpc(raw, 'tools/list').status_code == 401
    raw = issue(thandi)
    thandi.suspended_until = timezone.now() + dt.timedelta(days=1)
    thandi.save(update_fields=['suspended_until'])
    assert rpc(raw, 'tools/list').status_code == 401


def test_password_change_revokes_tokens(thandi):
    raw = issue(thandi)
    thandi.set_password('a-brand-new-password-123')
    thandi.save()
    assert rpc(raw, 'tools/list').status_code == 401
    assert PersonalAccessToken.objects.get().revoked_at is not None


def test_tokens_cannot_be_revoked_by_others(thandi, sipho):
    issue(thandi)
    token = PersonalAccessToken.objects.get()
    assert client_for(sipho).delete(f'/api/assistant/tokens/{token.id}/').status_code == 404
    assert PersonalAccessToken.objects.get().revoked_at is None


def test_origin_is_validated(thandi):
    raw = issue(thandi)
    assert rpc(raw, 'tools/list', headers={'HTTP_ORIGIN': 'https://evil.example'}).status_code == 403
    assert rpc(raw, 'tools/list', headers={'HTTP_ORIGIN': 'http://localhost:4200'}).status_code == 200


def test_modern_requests_validate_mirrored_headers(thandi):
    raw = issue(thandi)
    meta = {'_meta': {'io.modelcontextprotocol/protocolVersion': MODERN}}
    ok = rpc(raw, 'tools/list', meta, version=MODERN, headers={'HTTP_MCP_METHOD': 'tools/list'})
    assert ok.status_code == 200 and ok.json()['result']['tools']
    missing = rpc(raw, 'tools/list', meta, version=MODERN)
    assert missing.status_code == 400 and missing.json()['error']['code'] == -32020
    call = {**meta, 'name': 'list_my_groups', 'arguments': {}}
    wrong = rpc(raw, 'tools/call', call, version=MODERN,
                headers={'HTTP_MCP_METHOD': 'tools/call', 'HTTP_MCP_NAME': 'get_post'})
    assert wrong.status_code == 400 and wrong.json()['error']['code'] == -32020
    encoded = '=?base64?' + base64.b64encode(b'list_my_groups').decode() + '?='
    good = rpc(raw, 'tools/call', call, version=MODERN, headers={'HTTP_MCP_METHOD': 'tools/call',
                                                                 'HTTP_MCP_NAME': encoded})
    assert good.status_code == 200 and good.json()['result']['isError'] is False
    mismatch = rpc(raw, 'tools/list', meta, version='2025-11-25', headers={'HTTP_MCP_METHOD': 'tools/list'})
    assert mismatch.status_code == 400 and mismatch.json()['error']['code'] == -32020
    discover = rpc(raw, 'server/discover', meta, version=MODERN, headers={'HTTP_MCP_METHOD': 'server/discover'})
    assert MODERN in discover.json()['result']['supportedVersions']
    unknown = rpc(raw, 'resources/list', meta, version=MODERN, headers={'HTTP_MCP_METHOD': 'resources/list'})
    assert unknown.status_code == 404 and unknown.json()['error']['code'] == -32601


def test_unsupported_versions_and_malformed_requests(thandi):
    raw = issue(thandi)
    r = rpc(raw, 'tools/list', version='1900-01-01')
    assert r.status_code == 400 and r.json()['error']['code'] == -32022
    assert '2025-11-25' in r.json()['error']['data']['supported']
    assert rpc(raw, 'tools/list', version=None).json()['error']['code'] == -32022
    c = APIClient()
    r = c.post('/api/mcp/', 'not json', content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {raw}')
    assert r.status_code == 400 and r.json()['error']['code'] == -32700
    r = c.post('/api/mcp/', [{'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}], format='json',
               HTTP_AUTHORIZATION=f'Bearer {raw}')
    assert r.status_code == 400
    assert c.get('/api/mcp/', HTTP_AUTHORIZATION=f'Bearer {raw}').status_code == 405
    r = rpc(raw, 'tools/call', {'name': 'nope', 'arguments': {}})
    assert r.json()['error']['code'] == -32602


def test_mcp_is_rate_limited(thandi, monkeypatch):
    monkeypatch.setattr(MCPRateThrottle, 'default_rate', '3/min')
    raw = issue(thandi)
    codes = [rpc(raw, 'ping').status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
