import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _clear_cache():
    # Presence counters live in the cache; start every test with nobody online.
    cache.clear()
    yield
    cache.clear()
