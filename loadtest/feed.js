// Home feed reads: ranked first page, chronological first page, then the next page.
//   k6 run -e BASE_URL=http://localhost:4200 loadtest/feed.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { BASE_URL, authHeaders, loginAll, tokenFor } from './lib/auth.js';

export const options = {
  scenarios: {
    feed: {
      executor: 'ramping-vus',
      stages: [
        { duration: '30s', target: parseInt(__ENV.VUS || '50', 10) },
        { duration: __ENV.DURATION || '2m', target: parseInt(__ENV.VUS || '50', 10) },
        { duration: '15s', target: 0 },
      ],
    },
  },
  thresholds: {
    'http_req_failed{name:feed}': ['rate<0.01'],
    'http_req_duration{name:feed}': ['p(95)<500', 'p(99)<1200'],
    'http_req_duration{name:feed-next}': ['p(95)<600'],
  },
};

export function setup() {
  return { tokens: loginAll() };
}

export default function (data) {
  const params = authHeaders(tokenFor(data.tokens));
  const sort = Math.random() < 0.8 ? 'top' : 'latest';
  const first = http.get(`${BASE_URL}/api/posts/?feed=true&sort=${sort}`, { ...params, tags: { name: 'feed' } });
  check(first, { 'feed 200': (r) => r.status === 200 });
  const cursor = first.status === 200 ? first.json('next_cursor') : null;
  sleep(1 + Math.random() * 2); // reading
  if (cursor) {
    const next = http.get(`${BASE_URL}/api/posts/?feed=true&sort=${sort}&cursor=${encodeURIComponent(cursor)}`,
      { ...params, tags: { name: 'feed-next' } });
    check(next, { 'next page 200': (r) => r.status === 200 });
  }
  sleep(1 + Math.random() * 3);
}
