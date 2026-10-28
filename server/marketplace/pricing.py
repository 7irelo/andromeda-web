"""
Price suggestions from comparable listings.

The AI service describes the item but never prices it: prices come from what
similar things actually list and sell for here. Comparables are active,
reserved and sold listings in the same category and currency whose titles
share words with the draft, ranked by overlap. The suggestion is the median
with the interquartile range, or nothing when there's too little to go on.
"""
import re
import statistics

from django.db.models import Q

from core import visibility
from .models import Listing

MIN_COMPARABLES = 4
MAX_COMPARABLES = 30
CANDIDATES = 300
_WORD_RE = re.compile(r'[a-z0-9]+')
_STOPWORDS = {
    'and', 'the', 'for', 'with', 'new', 'used', 'good', 'condition', 'sale', 'like', 'very', 'great',
    'excellent', 'set', 'pair', 'item', 'size', 'colour', 'color', 'black', 'white', 'grey', 'gray',
}


def keywords(text, limit=8):
    words = [w for w in _WORD_RE.findall((text or '').lower()) if len(w) >= 3 and w not in _STOPWORDS]
    return list(dict.fromkeys(words))[:limit]


def quartiles(values):
    """(Q1, median, Q3) using the inclusive method, so small samples stay inside their range."""
    data = sorted(float(v) for v in values)
    q1, median, q3 = statistics.quantiles(data, n=4, method='inclusive')
    return q1, median, q3


def comparables(user, title, category, currency, exclude_id=None):
    """Listings similar to `title`, best match first. Removed listings and blocked sellers never count."""
    words = keywords(title)
    if not words:
        return []
    cond = Q()
    for w in words:
        cond |= Q(title__icontains=w)
    qs = Listing.objects.filter(cond, currency=currency, price__gt=0,
                                status__in=[*Listing.PUBLIC_STATUSES, Listing.STATUS_SOLD]) \
        .exclude(moderation_status='removed').exclude(seller_id__in=visibility.blocked_ids(user))
    if category is not None:
        qs = qs.filter(category=category)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    rows = qs.order_by('-created_at').values_list('id', 'title', 'price')[:CANDIDATES]
    # Rank by how many keywords each title shares; a lone shared word only counts for one-word titles.
    need = 1 if len(words) == 1 else 2
    scored = []
    for pk, other_title, price in rows:
        overlap = len(set(words) & set(keywords(other_title, limit=20)))
        if overlap >= need:
            scored.append((overlap, pk, price))
    scored.sort(key=lambda r: (-r[0], -r[1]))
    return [(pk, price) for _, pk, price in scored[:MAX_COMPARABLES]]


def suggest(user, title, category, currency):
    comps = comparables(user, title, category, currency)
    if len(comps) < MIN_COMPARABLES:
        return None
    q1, median, q3 = quartiles([price for _, price in comps])
    return {'low': round(q1, 2), 'median': round(median, 2), 'high': round(q3, 2),
            'currency': currency, 'based_on': len(comps)}
