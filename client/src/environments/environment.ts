export const environment = {
  production: false,
  apiUrl: '/api',
  wsUrl: `ws://${typeof window !== 'undefined' ? window.location.host : 'localhost'}/ws`,
  // Browser error reporting (Sentry); empty = off.
  sentryDsn: '',
};
