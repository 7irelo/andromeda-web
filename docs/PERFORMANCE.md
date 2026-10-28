# Performance and load testing

Three [k6](https://k6.io) scripts in `loadtest/` exercise the paths that carry
most of the load: reading the home feed, writing posts, and fanning chat
messages out over WebSockets. Query budgets for the main list endpoints are
enforced in the unit tests (`server/core/test_query_counts.py`), so N+1
regressions fail CI before they reach a load test.

## What's tested

| Script | Scenario | Thresholds (fail the run) |
|---|---|---|
| `loadtest/feed.js` | Ramping VUs read the ranked (80%) or chronological feed, then the next page | feed p95 < 500 ms, p99 < 1.2 s, errors < 1%; next page p95 < 600 ms |
| `loadtest/posting.js` | Constant arrival rate of new posts (default 10/s), each followed by a feed read | create p95 < 800 ms, errors < 1%; feed p95 < 500 ms |
| `loadtest/chat_fanout.js` | Every VU joins one large group chat with a single-use ticket; a few senders post 1 msg/s; every member records send-to-receive latency | fan-out p95 < 250 ms, p99 < 1 s; WebSocket connect p95 < 1 s; checks > 99% |

## Running them

Never against production: the seeder creates accounts that share one password.

1. Start a stack (`docker compose up -d`) and, for realistic numbers, run it
   with production-like settings: `DEBUG=False`, the same worker counts, and
   the throttles raised for the test only, in `.env`:

   ```
   THROTTLE_AUTH=10000/min
   THROTTLE_USER=100000/min
   THROTTLE_WRITE=100000/min
   THROTTLE_WS_TICKET=100000/min
   ```

2. Seed users, a social graph and the fan-out room:

   ```
   loadtest/seed.sh 200 100      # 200 users, 100 of them in the chat room; prints ROOM_ID
   ```

3. Run the scripts (k6 installed locally, or the pinned container image):

   ```
   k6 run -e BASE_URL=http://localhost:4200 -e VUS=50 loadtest/feed.js
   k6 run -e BASE_URL=http://localhost:4200 -e RATE=10 loadtest/posting.js
   k6 run -e BASE_URL=http://localhost:4200 -e ROOM_ID=<id> -e VUS=100 -e SENDERS=5 loadtest/chat_fanout.js

   # without a local k6:
   docker run --rm -i --network host -v "$PWD/loadtest:/scripts:ro" \
     grafana/k6:2.2.0@sha256:9bd01d6941fca969cb61bb57d2da5ee9b385fe2aa8881df3798c196564d6ace6 \
     run -e BASE_URL=http://localhost:4200 /scripts/feed.js
   ```

   Useful variables: `VUS`, `DURATION`, `RATE`, `SENDERS`, `SESSION_SECONDS`,
   `LOADTEST_USERS` (accounts signed in during setup), `LOADTEST_PASSWORD`.

4. Watch the **Andromeda – SLOs & Alerts** dashboard in Grafana while it runs
   (p95 latency, 5xx ratio, Celery queue depth, WebSocket disconnects), and
   the Jaeger UI (`--profile observability`) for slow traces.

## Results

Fill in one row per run; keep the commit, the stack size and the settings next
to the numbers so later runs are comparable.

| Date | Commit | Host / stack | Script | Load | p50 | p95 | p99 | Errors | Notes |
|---|---|---|---|---|---|---|---|---|---|
| | | | feed.js | 50 VUs, 2 min | | | | | |
| | | | posting.js | 10 posts/s, 2 min | | | | | |
| | | | chat_fanout.js | 100 members, 5 senders | | | | | |

**Not run yet.** k6 is not installed on the machine this was written on and
the stack was not running there, so the table is empty. The scripts were
parse-checked with `k6 inspect` (k6 2.2.0) only.

## Levers already in place

- **Feed:** Redis candidate inboxes with hybrid fan-out (`server/feedcache/`):
  pushed on write for normal audiences, merged at read time for authors,
  Pages and groups above `FEEDCACHE_FANOUT_THRESHOLD`. Candidates are still
  filtered through `core.visibility`, so the cache only ever accelerates.
- **Queries:** list endpoints have flat query counts (viewer relationships,
  memberships and likes are loaded once per response, `core/viewer_cache.py`).
- **Media:** large videos go straight to object storage (presigned POST), and
  images get WebP variants for `srcset`, so clients download the size they show.
- **Graph writes** are off the request path (transactional outbox, drained by beat).
