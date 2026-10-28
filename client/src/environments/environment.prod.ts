export const environment = {
  production: true,
  apiUrl: '/api',
  // Match the page's scheme: wss:// behind TLS, ws:// only for plain-HTTP local runs.
  wsUrl: `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`,
  // Browser error reporting (Sentry); empty = off. Set at image build time (SENTRY_FRONTEND_DSN).
  sentryDsn: '',
};
