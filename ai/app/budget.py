"""Per-user daily token budgets (Redis when configured, in-process otherwise)."""
import datetime as dt
import threading


class Budget:
    def __init__(self, daily_limit: int, redis_url: str | None = None):
        self.daily_limit = daily_limit
        self._redis = None
        if redis_url:
            import redis
            self._redis = redis.Redis.from_url(redis_url, socket_timeout=1)
        self._mem: dict[str, int] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(user_id: int) -> str:
        return f'ai-budget:{dt.date.today().isoformat()}:{user_id}'

    def used(self, user_id: int) -> int:
        key = self._key(user_id)
        if self._redis is not None:
            try:
                return int(self._redis.get(key) or 0)
            except Exception:
                return 0  # fail open on budget reads; spend is still metered
        return self._mem.get(key, 0)

    def has_room(self, user_id: int) -> bool:
        return self.used(user_id) < self.daily_limit

    def spend(self, user_id: int, tokens: int) -> None:
        key = self._key(user_id)
        if self._redis is not None:
            try:
                pipe = self._redis.pipeline()
                pipe.incrby(key, tokens)
                pipe.expire(key, 60 * 60 * 26)
                pipe.execute()
                return
            except Exception:  # noqa: S110 - fall through to the in-process counter
                pass
        with self._lock:
            self._mem[key] = self._mem.get(key, 0) + tokens
