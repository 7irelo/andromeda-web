import { Injectable, signal } from '@angular/core';

export type ThemePreference = 'system' | 'light' | 'dark';

const STORAGE_KEY = 'theme';

/**
 * Light / dark theme. "system" follows `prefers-color-scheme` (handled purely in CSS:
 * styles.scss applies the dark tokens under the media query unless `data-theme="light"`
 * is set). An explicit choice is stored in localStorage, which can be unavailable
 * (private mode, blocked storage), so every access is guarded.
 */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  readonly preference = signal<ThemePreference>('system');

  constructor() {
    this.apply(this.read());
  }

  /** True when the page currently renders dark, whichever way that was chosen. */
  isDark(): boolean {
    const pref = this.preference();
    if (pref !== 'system') return pref === 'dark';
    try {
      return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;
    } catch {
      return false;
    }
  }

  set(pref: ThemePreference): void {
    this.apply(pref);
    try {
      if (pref === 'system') localStorage.removeItem(STORAGE_KEY);
      else localStorage.setItem(STORAGE_KEY, pref);
    } catch {
      /* storage unavailable: the choice lasts for this page only */
    }
  }

  /** Flip between light and dark (from "system", flips away from what is showing now). */
  toggle(): void {
    this.set(this.isDark() ? 'light' : 'dark');
  }

  private read(): ThemePreference {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved === 'light' || saved === 'dark') return saved;
    } catch {
      /* ignore */
    }
    return 'system';
  }

  private apply(pref: ThemePreference): void {
    this.preference.set(pref);
    const root = document.documentElement;
    if (pref === 'system') root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', pref);
  }
}
