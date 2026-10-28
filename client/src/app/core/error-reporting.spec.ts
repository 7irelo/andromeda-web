import type { ErrorEvent } from '@sentry/angular';
import { scrubBreadcrumb, scrubEvent, stripQuery } from './error-reporting';

describe('error reporting scrubbing', () => {
  it('drops query strings and fragments', () => {
    expect(stripQuery('https://x.test/search?q=secret#top')).toBe('https://x.test/search');
  });

  it('removes the user, cookies, bodies, queries and auth headers', () => {
    const event = {
      type: undefined,
      user: { id: '42', email: 'a@b.c' },
      request: {
        url: 'https://x.test/messages/7?ticket=abc',
        cookies: { andromeda_refresh: '1' },
        data: { password: 'hunter2' },
        query_string: 'ticket=abc',
        headers: { Authorization: 'Bearer t', 'User-Agent': 'ua' },
      },
      breadcrumbs: [{ category: 'xhr', data: { url: '/api/search/?q=secret' } }],
    } as unknown as ErrorEvent;

    const out = scrubEvent(event);

    expect(out.user).toBeUndefined();
    expect(out.request?.url).toBe('https://x.test/messages/7');
    expect(out.request?.cookies).toBeUndefined();
    expect(out.request?.data).toBeUndefined();
    expect(out.request?.query_string).toBeUndefined();
    expect(out.request?.headers).toEqual({ 'User-Agent': 'ua' });
    expect(out.breadcrumbs?.[0].data?.['url']).toBe('/api/search/');
  });

  it('strips navigation breadcrumbs too', () => {
    const crumb = scrubBreadcrumb({ category: 'navigation', data: { from: '/a?x=1', to: '/b?y=2' } });
    expect(crumb.data).toEqual({ from: '/a', to: '/b' });
  });
});
