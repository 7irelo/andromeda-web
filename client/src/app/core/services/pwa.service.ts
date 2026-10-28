import { ApplicationRef, Injectable, Injector, NgZone, inject, signal } from '@angular/core';
import { SwUpdate, VersionReadyEvent } from '@angular/service-worker';
import { filter, first } from 'rxjs';

/** Chrome's install prompt event (not in lib.dom yet). */
interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

const UPDATE_CHECK_MS = 6 * 60 * 60 * 1000;

/**
 * Progressive web app glue: online/offline state, "new version available" prompt
 * (the service worker downloads updates in the background; we offer a reload),
 * and the browser's install prompt for the navbar menu.
 */
@Injectable({ providedIn: 'root' })
export class PwaService {
  private readonly swUpdate = inject(SwUpdate);
  private readonly appRef = inject(ApplicationRef);
  private readonly injector = inject(Injector);
  private readonly zone = inject(NgZone);

  readonly online = signal(typeof navigator === 'undefined' ? true : navigator.onLine);
  readonly canInstall = signal(false);
  private installEvent: BeforeInstallPromptEvent | null = null;
  private started = false;

  start(): void {
    if (this.started || typeof window === 'undefined') return;
    this.started = true;

    window.addEventListener('online', () => this.zone.run(() => this.online.set(true)));
    window.addEventListener('offline', () => this.zone.run(() => this.online.set(false)));

    window.addEventListener('beforeinstallprompt', (e) => {
      // Keep the event and offer "Install app" in the menu instead of the browser's mini-bar.
      e.preventDefault();
      this.zone.run(() => {
        this.installEvent = e as BeforeInstallPromptEvent;
        this.canInstall.set(true);
      });
    });
    window.addEventListener('appinstalled', () => this.zone.run(() => this.clearInstall()));

    if (!this.swUpdate.isEnabled) return;

    this.swUpdate.versionUpdates
      .pipe(filter((e): e is VersionReadyEvent => e.type === 'VERSION_READY'))
      .subscribe(() => this.offerReload());

    this.swUpdate.unrecoverable.subscribe(() => this.offerReload(true));

    // Look for a new build now and then once the app has settled (never while it boots).
    this.appRef.isStable.pipe(first((stable) => stable)).subscribe(() => {
      setInterval(() => this.swUpdate.checkForUpdate().catch(() => undefined), UPDATE_CHECK_MS);
    });
  }

  async install(): Promise<void> {
    const event = this.installEvent;
    if (!event) return;
    try {
      await event.prompt();
      await event.userChoice;
    } finally {
      // The event can only be used once either way.
      this.clearInstall();
    }
  }

  private clearInstall(): void {
    this.installEvent = null;
    this.canInstall.set(false);
  }

  private async offerReload(broken = false): Promise<void> {
    // Loaded on demand so the snack bar (and the overlay it needs) stays out of the initial bundle.
    const { MatSnackBar } = await import('@angular/material/snack-bar');
    const snackBar = this.injector.get(MatSnackBar);
    const message = broken
      ? $localize`:@@pwa.broken:This version of Andromeda can't continue. Reload to get the latest.`
      : $localize`:@@pwa.updateAvailable:A new version of Andromeda is available.`;
    snackBar
      .open(message, $localize`:@@pwa.reload:Reload`, { duration: broken ? undefined : 15000, politeness: 'polite' })
      .onAction()
      .subscribe(() => document.location.reload());
  }
}
