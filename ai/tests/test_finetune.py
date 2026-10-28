"""Offline pipeline pieces that don't need a GPU or keys: dataset builders and eval scoring."""
import json

import pytest

from evals import run_replies
from finetune.build_dpo import pairs
from finetune.build_sft import examples


def _conv(**kw):
    return {
        'conversation': 0,
        'messages': [
            {'i': 0, 'speaker': 'Person 1', 'text': 'Braai on Saturday?'},
            {'i': 1, 'speaker': 'Person 2', 'text': 'Yes! What time?'},
            {'i': 2, 'speaker': 'Person 2', 'text': 'I can bring wood'},
            {'i': 3, 'speaker': 'Person 1', 'text': 'From 2. Call me on 071 999 8888'},
            {'i': 4, 'speaker': 'Person 2', 'text': 'Great, see you then'},
        ],
        'suggestion_sets': [], **kw,
    }


def test_sft_pairs_context_with_the_reply_actually_sent():
    rows = list(examples([_conv()]))
    # i=2 follows its own sender and i=3 has a phone number: neither becomes a target.
    targets = [json.loads(r['messages'][2]['content'])['suggestions'] for r in rows]
    assert targets == [['Yes! What time?'], ['Great, see you then']]
    system, user = rows[1]['messages'][0]['content'], rows[1]['messages'][1]['content']
    assert 'three short replies' in system and 'Viewer: Person 2' in user
    assert user.count('<untrusted') == 4 and 'sender="viewer"' in user and 'Great, see you' not in user
    assert {r['split'] for r in rows} <= {'train', 'eval'}


@pytest.mark.parametrize('bad', [
    {'speaker': 'Thandi Dlamini'}, {'text': 'mail demo4 at demo4@example.test'}, {'text': 'hi demo12'},
])
def test_builders_refuse_unpseudonymised_exports(bad):
    conv = _conv()
    conv['messages'][0].update(bad)
    with pytest.raises(SystemExit):
        list(examples([conv]))
    with pytest.raises(SystemExit):
        list(pairs([conv]))


def test_dpo_prefers_accepted_and_edited_over_dismissed_and_ignored():
    sets = [
        {'viewer': 'Person 2', 'anchor': 0, 'variant': 'haiku', 'shown': [
            {'text': 'Yes! What time?', 'action': 'accepted'}, {'text': 'No thanks', 'action': 'dismissed'},
            {'text': 'Maybe', 'action': 'ignored'}]},
        {'viewer': 'Person 2', 'anchor': 3, 'variant': 'luna', 'shown': [
            {'text': 'See you!', 'action': 'edited'}, {'text': 'Who is this?', 'action': 'ignored'}]},
        # Real users' sets never carry text, so they can't produce pairs.
        {'viewer': 'Person 1', 'anchor': 1, 'variant': 'haiku', 'shown': [
            {'text': None, 'action': 'accepted'}, {'text': None, 'action': 'dismissed'}]},
    ]
    rows = list(pairs([_conv(suggestion_sets=sets)]))
    got = [(json.loads(r['chosen'][0]['content'])['suggestions'][0],
            json.loads(r['rejected'][0]['content'])['suggestions'][0], r['variant']) for r in rows]
    assert got == [('Yes! What time?', 'No thanks', 'haiku'), ('Yes! What time?', 'Maybe', 'haiku'),
                   ('Great, see you then', 'Who is this?', 'luna')]
    assert rows[0]['prompt'][1]['content'].count('<untrusted') == 1


def test_eval_dataset_is_valid_and_covers_the_languages():
    rows = run_replies.load()
    assert len(rows) == 30 and len({r['id'] for r in rows}) == 30
    for row in rows:
        run_replies.request_for(row, 'haiku')  # validates
    assert {'en', 'af', 'zu', 'st', 'xh'} <= {lang for r in rows for lang in r['lang'].split('/')}


def test_eval_judges_are_cross_family():
    assert run_replies.judges_for('haiku', 'lora') == ['openai']
    assert run_replies.judges_for('luna', 'lora') == ['anthropic']
    assert sorted(run_replies.judges_for('haiku', 'luna')) == ['anthropic', 'openai']


def test_eval_position_swap_only_counts_consistent_wins():
    assert run_replies.combine('1', '2') == 'a'
    assert run_replies.combine('2', '1') == 'b'
    assert run_replies.combine('1', '1') == 'tie'  # always picked the first slot: position bias
    assert run_replies.combine('tie', '2') == 'tie'


def test_eval_report_and_leak_check():
    row = {'messages': [{'id': 1, 'sender': 's', 'text': 'call 082 555 1234'}]}
    assert run_replies.leaks(['Sure, calling 082 555 1234', 'Mail me at x@y.example'], row) == 1
    results = [{'a': ['x'], 'b': [], 'latency': (0.2, 0.3), 'cost': 0.001, 'errors': (None, None),
                'outcomes': {'openai': o}, 'flagged': 0, 'leaks': 0} for o in ('a', 'a', 'b', 'tie')]
    s = run_replies.report('haiku', 'lora', ['openai'], results)
    assert s['judges']['openai'] == {'wins_a': 2, 'wins_b': 1, 'ties': 1, 'win_rate_a': 0.625}
    assert s['empty_rate'] == {'haiku': 0.0, 'lora': 1.0} and s['flagged_suggestions'] == 0
