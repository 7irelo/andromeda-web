import { safeReturnUrl } from './auth.guard';

describe('safeReturnUrl', () => {
  it('keeps same-app paths', () => {
    expect(safeReturnUrl('/groups/join/abc')).toBe('/groups/join/abc');
  });

  it('refuses anything that could leave the app', () => {
    for (const bad of ['//evil.example', 'https://evil.example', '/\\evil.example', 'javascript:alert(1)', '', null]) {
      expect(safeReturnUrl(bad)).toBe('/feed');
    }
  });

  it('does not loop back to the login page', () => {
    expect(safeReturnUrl('/login?returnUrl=/feed')).toBe('/feed');
  });
});
