"""
Sticky A/B buckets.

A user's variant is a pure function of their id and the experiment name, so
it is the same on every request and every process without storing anything,
and different experiments split users independently of each other.
"""
import hashlib

SLOTS = 10000


def bucket(user_id, experiment: str, variants: dict[str, float]) -> str:
    """
    The variant ``user_id`` falls into: sha256 of ``"{experiment}:{user_id}"``
    mod 10000, matched against the cumulative weights (in dict order). Weights
    need not sum to 100; they are scaled to the 10000 slots.
    """
    weights = [(name, float(w)) for name, w in variants.items() if float(w) > 0]
    if not weights:
        raise ValueError('An experiment needs at least one variant with a positive weight.')
    total = sum(w for _, w in weights)
    slot = int(hashlib.sha256(f'{experiment}:{user_id}'.encode()).hexdigest(), 16) % SLOTS
    cumulative = 0.0
    for name, w in weights:
        cumulative += w / total * SLOTS
        if slot < cumulative:
            return name
    return weights[-1][0]  # float rounding on the last edge
