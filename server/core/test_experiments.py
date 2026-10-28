from collections import Counter

import pytest

from core.experiments import bucket


def test_bucket_is_sticky_and_deterministic():
    variants = {'a': 50, 'b': 50}
    assert all(bucket(42, 'exp', variants) == bucket(42, 'exp', variants) for _ in range(5))


def test_weights_are_respected():
    counts = Counter(bucket(uid, 'exp', {'a': 80, 'b': 20}) for uid in range(5000))
    assert 0.77 < counts['a'] / 5000 < 0.83


def test_zero_weight_variant_never_assigned():
    assert {bucket(uid, 'exp', {'a': 100, 'b': 0}) for uid in range(500)} == {'a'}


def test_experiments_split_independently():
    a = [bucket(uid, 'one', {'x': 50, 'y': 50}) for uid in range(2000)]
    b = [bucket(uid, 'two', {'x': 50, 'y': 50}) for uid in range(2000)]
    agree = sum(1 for p, q in zip(a, b, strict=True) if p == q) / 2000
    assert 0.45 < agree < 0.55


def test_known_value_matches_sha256_mod_10000():
    import hashlib
    slot = int(hashlib.sha256(b'feed_ranker:7').hexdigest(), 16) % 10000
    assert bucket(7, 'feed_ranker', {'v1': 50, 'v2': 50}) == ('v1' if slot < 5000 else 'v2')


def test_needs_a_positive_weight():
    with pytest.raises(ValueError):
        bucket(1, 'exp', {'a': 0})
