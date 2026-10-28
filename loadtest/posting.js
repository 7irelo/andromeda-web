// Writing posts (fan-out on write, moderation queueing, hashtags), mixed with feed reads.
//   k6 run -e BASE_URL=http://localhost:4200 loadtest/posting.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { BASE_URL, authHeaders, loginAll, tokenFor } from './lib/auth.js';

export const options = {
  scenarios: {
    posting: {
      executor: 'constant-arrival-rate',
      rate: parseInt(__ENV.RATE || '10', 10),   // posts per second across all VUs
      timeUnit: '1s',
      duration: __ENV.DURATION || '2m',
      preAllocatedVUs: 20,
      maxVUs: 100,
    },
  },
  thresholds: {
    'http_req_failed{name:create-post}': ['rate<0.01'],
    'http_req_duration{name:create-post}': ['p(95)<800'],
    'http_req_duration{name:feed}': ['p(95)<500'],
  },
};

export function setup() {
  return { tokens: loginAll() };
}

const TAGS = ['running', 'braai', 'coding', 'jazz', 'coffee'];

export default function (data) {
  const params = authHeaders(tokenFor(data.tokens));
  const tag = TAGS[Math.floor(Math.random() * TAGS.length)];
  const res = http.post(`${BASE_URL}/api/posts/`,
    JSON.stringify({ content: `k6 load test post #${tag} ${Date.now()}`, privacy: 'friends' }),
    { ...params, tags: { name: 'create-post' } });
  check(res, { 'post 201': (r) => r.status === 201 });
  // The author usually looks at their feed right after posting.
  const feed = http.get(`${BASE_URL}/api/posts/?feed=true&sort=latest`, { ...params, tags: { name: 'feed' } });
  check(feed, { 'feed 200': (r) => r.status === 200 });
  sleep(0.5);
}
