"""
Sticky A/B bucketing.

    variant = bucket(user.id, 'smart_replies_v1', {'haiku': 50, 'luna': 50})

A user lands in the same variant every time for a given experiment (no
storage needed), and independently across experiments, because the slot is
``sha256(f'{experiment}:{user_id}') % 100``. Weights are relative and needn't
sum to 100; they're scaled onto the 100 slots in the order given, so keep the
order stable or users will move between variants. A weight of 0 switches a
variant off.
"""
import hashlib

SLOTS = 100


def slot(user_id, experiment):
    """The user's position, 0-99, in this experiment."""
    digest = hashlib.sha256(f'{experiment}:{user_id}'.encode()).digest()
    return int.from_bytes(digest[:8], 'big') % SLOTS


def bucket(user_id, experiment, variants):
    """The user's variant name. ``variants`` maps each name to a non-negative weight."""
    if not experiment or not variants:
        raise ValueError('An experiment needs a name and at least one variant.')
    weights = list(variants.items())
    if any(not isinstance(w, (int, float)) or w < 0 for _, w in weights):
        raise ValueError('Variant weights must be non-negative numbers.')
    total = sum(w for _, w in weights)
    if total <= 0:
        raise ValueError('At least one variant needs a positive weight.')
    position = slot(user_id, experiment)
    upper = 0.0
    for name, weight in weights:
        upper += weight * SLOTS / total
        if position < upper:
            return name
    # Floating-point rounding can leave the last slot uncovered: give it to the last live variant.
    return next(name for name, weight in reversed(weights) if weight > 0)
