"""Per-user daily token budgets (Redis when configured, in-process otherwise)."""
import datetime as dt
import threading


class Budget:
    # User id 0 is Django itself (background indexing), with its own allowance.
    SYSTEM_USER = 0

    def __init__(self, daily_limit: int, redis_url: str | None = None, system_daily_limit: int | None = None,
                 daily_audio_seconds: int = 1800):
        self.daily_limit = daily_limit
        self.daily_audio_seconds = daily_audio_seconds
        self.system_daily_limit = system_daily_limit if system_daily_limit is not None else daily_limit
        self._redis = None
        if redis_url:
            import redis
            self._redis = redis.Redis.from_url(redis_url, socket_timeout=1)
        self._mem: dict[str, int] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(user_id: int, kind: str = 'tokens') -> str:
        prefix = 'ai-budget' if kind == 'tokens' else f'ai-budget-{kind}'
        return f'{prefix}:{dt.date.today().isoformat()}:{user_id}'

    def used(self, user_id: int, kind: str = 'tokens') -> int:
        key = self._key(user_id, kind)
        if self._redis is not None:
            try:
                return int(self._redis.get(key) or 0)
            except Exception:
                return 0  # fail open on budget reads; spend is still metered
        return self._mem.get(key, 0)

    def has_room(self, user_id: int) -> bool:
        limit = self.system_daily_limit if user_id == self.SYSTEM_USER else self.daily_limit
        return self.used(user_id) < limit

    def has_audio_room(self, user_id: int) -> bool:
        return user_id == self.SYSTEM_USER or self.used(user_id, 'audio') < self.daily_audio_seconds

    def spend_audio(self, user_id: int, seconds: float) -> None:
        self.spend(user_id, int(seconds + 0.999), kind='audio')

    def spend(self, user_id: int, tokens: int, kind: str = 'tokens') -> None:
        key = self._key(user_id, kind)
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
