import { TestBed } from '@angular/core/testing';
import { ThemeService } from './theme.service';

describe('ThemeService', () => {
  const root = document.documentElement;

  afterEach(() => {
    root.removeAttribute('data-theme');
    try { localStorage.removeItem('theme'); } catch { /* ignore */ }
  });

  it('follows the system theme by default', () => {
    const theme = TestBed.inject(ThemeService);
    expect(theme.preference()).toBe('system');
    expect(root.hasAttribute('data-theme')).toBeFalse();
  });

  it('applies and remembers an explicit choice', () => {
    TestBed.inject(ThemeService).set('dark');
    expect(root.getAttribute('data-theme')).toBe('dark');
    expect(localStorage.getItem('theme')).toBe('dark');
  });

  it('restores the saved choice on start', () => {
    localStorage.setItem('theme', 'light');
    const theme = TestBed.inject(ThemeService);
    expect(theme.preference()).toBe('light');
    expect(root.getAttribute('data-theme')).toBe('light');
    expect(theme.isDark()).toBeFalse();
  });

  it('going back to "system" clears the stored choice', () => {
    const theme = TestBed.inject(ThemeService);
    theme.set('dark');
    theme.set('system');
    expect(localStorage.getItem('theme')).toBeNull();
    expect(root.hasAttribute('data-theme')).toBeFalse();
  });

  it('still switches when storage is unavailable', () => {
    spyOn(Storage.prototype, 'getItem').and.throwError('SecurityError');
    spyOn(Storage.prototype, 'setItem').and.throwError('QuotaExceededError');
    const theme = TestBed.inject(ThemeService);
    expect(() => theme.set('dark')).not.toThrow();
    expect(root.getAttribute('data-theme')).toBe('dark');
    expect(theme.isDark()).toBeTrue();
  });

  it('toggle flips between light and dark', () => {
    const theme = TestBed.inject(ThemeService);
    theme.set('light');
    theme.toggle();
    expect(theme.preference()).toBe('dark');
    theme.toggle();
    expect(theme.preference()).toBe('light');
  });
});
