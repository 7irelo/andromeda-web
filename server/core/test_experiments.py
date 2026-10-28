from collections import Counter

import pytest

from core.experiments import bucket, slot


def test_assignment_is_sticky_and_within_the_variants():
    variants = {'haiku': 50, 'luna': 50}
    for uid in range(200):
        first = bucket(uid, 'smart_replies_v1', variants)
        assert first in variants
        assert all(bucket(uid, 'smart_replies_v1', variants) == first for _ in range(3))
        assert 0 <= slot(uid, 'smart_replies_v1') < 100


def test_split_follows_the_weights():
    counts = Counter(bucket(uid, 'exp', {'a': 80, 'b': 20}) for uid in range(5000))
    assert 0.76 < counts['a'] / 5000 < 0.84
    counts = Counter(bucket(uid, 'exp', {'a': 1, 'b': 1, 'c': 2}) for uid in range(4000))
    assert 0.45 < counts['c'] / 4000 < 0.55


def test_experiments_are_independent():
    a = [bucket(uid, 'smart_replies_v1', {'x': 50, 'y': 50}) for uid in range(2000)]
    b = [bucket(uid, 'feed_ranking_v1', {'x': 50, 'y': 50}) for uid in range(2000)]
    agreement = sum(1 for p, q in zip(a, b) if p == q) / 2000
    assert 0.4 < agreement < 0.6


def test_zero_weight_turns_a_variant_off_and_full_weight_takes_everyone():
    assert {bucket(uid, 'e', {'on': 100, 'off': 0}) for uid in range(500)} == {'on'}
    assert {bucket(uid, 'e', {'off': 0, 'on': 1}) for uid in range(500)} == {'on'}


def test_growing_a_variant_only_moves_users_into_it():
    before = {uid: bucket(uid, 'rollout', {'new': 10, 'old': 90}) for uid in range(2000)}
    after = {uid: bucket(uid, 'rollout', {'new': 30, 'old': 70}) for uid in range(2000)}
    assert all(after[uid] == 'new' for uid, v in before.items() if v == 'new')


@pytest.mark.parametrize('args', [
    ('', {'a': 1}), ('e', {}), ('e', {'a': 0}), ('e', {'a': -1, 'b': 2}), ('e', {'a': 'fifty'}),
])
def test_rejects_bad_definitions(args):
    with pytest.raises(ValueError):
        bucket(1, *args)
