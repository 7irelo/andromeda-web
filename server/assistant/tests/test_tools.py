"""Tool behaviour as the viewer: visibility, validation and model-readable results."""
import json

import pytest

from assistant import tools
from assistant.models import Proposal
from chats.tests.helpers import make_room
from core.test_security import make_user
from groups.models import Group, GroupMember
from marketplace.models import Listing
from posts.models import Post
from users.models import Block

pytestmark = pytest.mark.django_db


def run_tool(user, name, **args):
    out = tools.execute(name, args, tools.Context(user=user))
    return out, (json.loads(out.content) if not out.is_error else out.content)


def test_schemas_match_the_validators():
    for tool in tools.TOOLS.values():
        assert set(tool.schema['properties']) == set(tool.args().fields), tool.name
        assert tool.schema['additionalProperties'] is False
        assert len(tool.description) < 300 and tool.description == tool.description.strip()
    assert {t.name for t in tools.TOOLS.values() if t.writes} == {'create_post', 'send_message'}
    assert {t['name'] for t in tools.specs(('read',))} == set(tools.TOOLS) - {'create_post', 'send_message'}


def test_invalid_arguments_are_explained(thandi):
    out, err = run_tool(thandi, 'get_post', id='abc')
    assert out.is_error and err.startswith('Invalid arguments. id:')
    out = tools.execute('search_content', ['not', 'an', 'object'], tools.Context(user=thandi))
    assert out.is_error and 'JSON object' in out.content
    out, err = run_tool(thandi, 'send_message', text='hi')
    assert 'exactly one of to_user_id or room_id' in err


def test_search_content_only_returns_visible_items(thandi, sipho):
    Post.objects.create(author=sipho, content='braai on saturday at the park')
    Post.objects.create(author=sipho, content='braai secret plans', privacy=Post.PRIVACY_PRIVATE)
    blocked = make_user('blocked')
    Post.objects.create(author=blocked, content='braai from a blocked person')
    Block.objects.create(blocker=thandi, blocked=blocked)
    opted = make_user('optedout', ai_opt_out=True)
    Post.objects.create(author=opted, content='braai from someone who opted out')
    out, data = run_tool(thandi, 'search_content', query='braai')
    texts = ' '.join(r['text'] for r in data['results'])
    assert 'saturday at the park' in texts
    assert 'secret' not in texts and 'blocked person' not in texts and 'opted out' not in texts
    assert [c['type'] for c in out.citations] == ['posts']


def test_get_post_and_ai_opt_out(thandi, sipho):
    post = Post.objects.create(author=sipho, content='Hello')
    _, data = run_tool(thandi, 'get_post', id=post.id)
    assert data['text'] == 'Hello' and data['author'] == 'sipho'
    sipho.ai_opt_out = True
    sipho.save(update_fields=['ai_opt_out'])
    out, err = run_tool(thandi, 'get_post', id=post.id)
    assert out.is_error and 'turned off AI' in err


def test_listing_search_filters_price_and_distance(thandi, sipho):
    Listing.objects.create(seller=sipho, title='Couch', description='Grey couch', price=1500, location='Cape Town',
                           latitude=-33.92, longitude=18.42)
    Listing.objects.create(seller=sipho, title='Fancy couch', description='Leather', price=9000,
                           location='Cape Town', latitude=-33.92, longitude=18.42)
    Listing.objects.create(seller=sipho, title='Durban couch', description='Blue couch', price=1000,
                           location='Durban', latitude=-29.86, longitude=31.02)
    _, data = run_tool(thandi, 'search_listings', query='couch', max_price='2000')
    assert {x['title'] for x in data['listings']} == {'Couch', 'Durban couch'}
    out, err = run_tool(thandi, 'search_listings', query='couch', near_me=True)
    assert out.is_error and 'city' in err
    thandi.location = 'Sea Point, Cape Town'
    thandi.save(update_fields=['location'])
    _, data = run_tool(thandi, 'search_listings', query='couch', near_me=True, max_price=5000)
    assert [x['title'] for x in data['listings']] == ['Couch']


def test_groups_chats_and_people(thandi, sipho):
    group = Group.objects.create(name='Runners', privacy=Group.PRIVACY_SECRET, created_by=sipho)
    GroupMember.objects.create(group=group, user=thandi)
    _, data = run_tool(thandi, 'list_my_groups')
    assert data['groups'] == [{'id': group.id, 'name': 'Runners', 'privacy': 'secret', 'role': 'member'}]
    blocked = make_user('blockedfriend')
    room = make_room(thandi, sipho, blocked, name='Crew')
    Block.objects.create(blocker=blocked, blocked=thandi)
    _, data = run_tool(thandi, 'list_my_chats')
    assert data['chats'] == [{'room_id': room.id, 'name': 'Crew', 'type': 'group', 'with': ['sipho']}]
    _, data = run_tool(thandi, 'find_people', query='sip')
    assert data['people'][0]['username'] == 'sipho' and data['people'][0]['can_message'] is True
    _, data = run_tool(thandi, 'find_people', query='blockedfriend')
    assert data['people'] == []


def test_drafts_preview_without_side_effects(thandi, sipho):
    _, data = run_tool(thandi, 'draft_message', to_user_id=sipho.id, text='See https://x.example soon')
    assert data['draft']['to'][0]['username'] == 'sipho' and data['draft']['links'] == ['https://x.example']
    _, data = run_tool(thandi, 'draft_post', text='Hello', privacy='friends')
    assert data['draft']['audience'] == 'Friends'
    assert not Proposal.objects.exists()


def test_pending_proposals_are_capped(thandi):
    for _ in range(tools.MAX_PENDING_PROPOSALS):
        assert not run_tool(thandi, 'create_post', text='hi')[0].is_error
    out, err = run_tool(thandi, 'create_post', text='one too many')
    assert out.is_error and 'Too many proposals' in err
