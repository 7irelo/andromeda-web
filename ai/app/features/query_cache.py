"""
Semantic cache for search-query rewrites.

A rewrite costs a model call and over a second; embedding the query costs
almost nothing and happens anyway. So: embed, then reuse the plan of an earlier
query when the text matches exactly or the vectors are close enough.

Plans hold no private data, but a query can name a person, so plans with an
author are never stored and the cache can't pass one member's lookup to another.
The threshold comes from `evals/run_query_cache.py`, which measures false hits
on near-miss pairs ("couch in Durban" / "couch in Joburg").

Comparison uses the first 256 dimensions, renormalised: text-embedding-3 models
are built to be shortened this way, and it keeps a scan of the cache cheap.
"""
import math
from collections import OrderedDict
from dataclasses import dataclass

COMPARE_DIMS = 256
DEFAULT_THRESHOLD = 0.94
DEFAULT_MAX_ENTRIES = 500


def normalise(query: str) -> str:
    return ' '.join(query.casefold().split())


def shorten(vector: list[float]) -> list[float]:
    head = vector[:COMPARE_DIMS]
    norm = math.sqrt(sum(x * x for x in head)) or 1.0
    return [x / norm for x in head]


def similarity(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


@dataclass
class Entry:
    key_vector: list[float]
    value: object


class QueryCache:
    """An in-process LRU, per worker. Losing it costs only a few rewrites."""

    def __init__(self, threshold: float = DEFAULT_THRESHOLD, max_entries: int = DEFAULT_MAX_ENTRIES):
        self.threshold = threshold
        self.max_entries = max_entries
        self._entries: OrderedDict[str, Entry] = OrderedDict()

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, query: str, vector: list[float]) -> tuple[object, str] | None:
        """The cached value and how it matched ('exact' or 'semantic'), or None."""
        key = normalise(query)
        entry = self._entries.get(key)
        if entry is not None:
            self._entries.move_to_end(key)
            return entry.value, 'exact'
        short = shorten(vector)
        best_key, best_score = None, self.threshold
        for k, e in self._entries.items():
            score = similarity(short, e.key_vector)
            if score >= best_score:
                best_key, best_score = k, score
        if best_key is None:
            return None
        self._entries.move_to_end(best_key)
        return self._entries[best_key].value, 'semantic'

    def put(self, query: str, vector: list[float], value: object) -> None:
        key = normalise(query)
        self._entries[key] = Entry(shorten(vector), value)
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)
