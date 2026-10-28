"""
Per-user inbox lists of candidate post ids.

On Redis (``django_redis``) each inbox is a list, newest first, capped at
``FEEDCACHE_MAX_ITEMS``. Pushes use ``LPUSHX`` so they only ever extend an
inbox that was built in full from the database: a missing key means "cold,
rebuild", never "empty". A built inbox always holds a ``0`` sentinel so an
empty feed is still distinguishable from a cold one.

Without Redis (tests run on locmem) the same contract is kept with plain
cache get/set, which is fine for a single process.
"""
from django.conf import settings
from django.core.cache import cache

SENTINEL = 0


def _key(user_id):
    return f'feedcache:inbox:{int(user_id)}'


def _max():
    return settings.FEEDCACHE_MAX_ITEMS


def _ttl():
    return settings.FEEDCACHE_TTL_SECONDS


class RedisStore:
    def __init__(self, client, prefix):
        self.r = client
        self.prefix = prefix

    def _k(self, user_id):
        return f'{self.prefix}:{_key(user_id)}' if self.prefix else _key(user_id)

    def read(self, user_id, limit):
        key = self._k(user_id)
        pipe = self.r.pipeline()
        pipe.exists(key)
        pipe.lrange(key, 0, max(0, limit - 1))
        exists, raw = pipe.execute()
        if not exists:
            return None
        return [int(v) for v in raw if int(v) != SENTINEL]

    def build(self, user_id, ids):
        key = self._k(user_id)
        pipe = self.r.pipeline(transaction=True)
        pipe.delete(key)
        pipe.rpush(key, *[int(i) for i in ids[:_max()]], SENTINEL)
        pipe.expire(key, _ttl())
        pipe.execute()

    def push(self, user_ids, post_id):
        pipe = self.r.pipeline(transaction=False)
        for uid in user_ids:
            key = self._k(uid)
            pipe.lpushx(key, int(post_id))
            pipe.ltrim(key, 0, _max() - 1)
        pipe.execute()

    def remove(self, user_ids, post_id):
        pipe = self.r.pipeline(transaction=False)
        for uid in user_ids:
            pipe.lrem(self._k(uid), 0, int(post_id))
        pipe.execute()

    def drop(self, user_ids):
        keys = [self._k(uid) for uid in user_ids]
        if keys:
            self.r.delete(*keys)


class CacheStore:
    """Fallback on any Django cache backend (locmem in tests). Not atomic across processes."""

    def read(self, user_id, limit):
        items = cache.get(_key(user_id))
        if items is None:
            return None
        return [i for i in items if i != SENTINEL][:limit]

    def build(self, user_id, ids):
        cache.set(_key(user_id), [int(i) for i in ids[:_max()]] + [SENTINEL], _ttl())

    def push(self, user_ids, post_id):
        for uid in user_ids:
            items = cache.get(_key(uid))
            if items is not None:
                cache.set(_key(uid), ([int(post_id)] + items)[:_max()], _ttl())

    def remove(self, user_ids, post_id):
        for uid in user_ids:
            items = cache.get(_key(uid))
            if items is not None:
                cache.set(_key(uid), [i for i in items if i != int(post_id)], _ttl())

    def drop(self, user_ids):
        cache.delete_many([_key(uid) for uid in user_ids])


_store = None


def get_store():
    global _store
    if _store is None:
        try:
            from django_redis import get_redis_connection

            client = get_redis_connection('default')
            _store = RedisStore(client, settings.CACHES['default'].get('KEY_PREFIX', ''))
        except (ImportError, NotImplementedError, AttributeError, KeyError):
            _store = CacheStore()
    return _store


def reset_store():
    global _store
    _store = None
