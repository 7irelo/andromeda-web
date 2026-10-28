// Chat fan-out over WebSockets: every VU joins one large group room (single-use
// ticket auth); a few VUs send messages stamped with the send time and every
// member measures how long each message took to reach them.
//
//   k6 run -e BASE_URL=http://localhost:4200 -e ROOM_ID=<from seed_loadtest> loadtest/chat_fanout.js
import ws from 'k6/ws';
import { check, fail } from 'k6';
import { Counter, Trend } from 'k6/metrics';
import { BASE_URL, WS_URL, loginAll, tokenFor, wsTicket } from './lib/auth.js';

const VUS = parseInt(__ENV.VUS || '50', 10);
const SENDERS = parseInt(__ENV.SENDERS || '5', 10);
const SESSION_MS = parseInt(__ENV.SESSION_SECONDS || '60', 10) * 1000;

const fanoutLatency = new Trend('chat_fanout_latency', true);
const received = new Counter('chat_messages_received');
const sent = new Counter('chat_messages_sent');
const rateLimited = new Counter('chat_rate_limited');

export const options = {
  scenarios: {
    members: { executor: 'per-vu-iterations', vus: VUS, iterations: 1, maxDuration: `${SESSION_MS / 1000 + 60}s` },
  },
  thresholds: {
    chat_fanout_latency: ['p(95)<250', 'p(99)<1000'],
    ws_connecting: ['p(95)<1000'],
    checks: ['rate>0.99'],
  },
};

export function setup() {
  if (!__ENV.ROOM_ID) {
    fail('Set ROOM_ID (printed by manage.py seed_loadtest).');
  }
  return { tokens: loginAll(VUS), room: __ENV.ROOM_ID };
}

export default function (data) {
  const ticket = wsTicket(tokenFor(data.tokens));
  const url = `${WS_URL}/ws/chat/${data.room}/?ticket=${ticket}`;
  // Channels checks Origin against ALLOWED_HOSTS.
  const res = ws.connect(url, { headers: { Origin: BASE_URL } }, (socket) => {
    const isSender = __VU <= SENDERS;
    socket.on('open', () => {
      if (isSender) {
        // 1 message/s per sender: under the consumer's 2/s token bucket.
        socket.setInterval(() => {
          socket.send(JSON.stringify({ type: 'message', content: `k6:${Date.now()}` }));
          sent.add(1);
        }, 1000);
      }
      socket.setTimeout(() => socket.close(1000), SESSION_MS);
    });
    socket.on('message', (raw) => {
      const frame = JSON.parse(raw);
      if (frame.type === 'message' && frame.message && /^k6:\d+$/.test(frame.message.content || '')) {
        fanoutLatency.add(Date.now() - parseInt(frame.message.content.slice(3), 10));
        received.add(1);
      } else if (frame.type === 'error' && frame.code === 'rate_limited') {
        rateLimited.add(1);
      }
    });
  });
  check(res, { 'ws upgraded (101)': (r) => r && r.status === 101 });
}
