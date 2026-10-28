import { Component, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { CommonModule } from '@angular/common';
import { NavbarComponent } from './shared/components/navbar/navbar.component';
import { AuthService } from './core/services/auth.service';
import { WebSocketService } from './core/services/websocket.service';
import { PwaService } from './core/services/pwa.service';
import { ThemeService } from './core/services/theme.service';

@Component({
    selector: 'app-root',
    imports: [RouterOutlet, CommonModule, NavbarComponent],
    template: `
    <a class="skip-link" href="#main-content" (click)="skipToContent($event)" i18n="@@shell.skipToContent">Skip to content</a>
    <app-navbar *ngIf="authService.isLoggedIn()"></app-navbar>
    <div class="offline-banner" *ngIf="!pwa.online()" role="status">
      <span class="material-icons" aria-hidden="true">cloud_off</span>
      <span i18n="@@shell.offline">You're offline. Things you've already opened still work; new content will load when you reconnect.</span>
    </div>
    <main id="main-content" tabindex="-1" [class.with-nav]="authService.isLoggedIn()">
      <router-outlet></router-outlet>
    </main>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    main { min-height: 100vh; }
    main:focus { outline: none; }
    main.with-nav {
      padding-top: 56px;
      padding-bottom: calc(var(--bottom-nav-height) + env(safe-area-inset-bottom, 0px));
    }
    .offline-banner {
      position: fixed; left: 50%; transform: translateX(-50%); z-index: 150;
      bottom: calc(var(--bottom-nav-height) + env(safe-area-inset-bottom, 0px) + 12px);
      display: flex; align-items: center; gap: 8px; max-width: calc(100vw - 32px);
      padding: 10px 16px; border-radius: var(--radius-md);
      background: #1e293b; color: #f1f5f9; box-shadow: var(--shadow-lg); font-size: var(--font-size-sm);
    }
  `]
})
export class AppComponent implements OnInit {
  constructor(
    public authService: AuthService,
    private wsService: WebSocketService,
    public pwa: PwaService,
    // Injected for its side effect: applies the saved light/dark choice before first paint.
    _theme: ThemeService,
  ) {}

  ngOnInit(): void {
    this.pwa.start();
    if (this.authService.isLoggedIn()) {
      this.wsService.connectNotifications();
    }
    this.authService.currentUser$.subscribe((user) => {
      if (user) this.wsService.connectNotifications();
      else this.wsService.disconnect();
    });
  }

  /** Move focus (not just scroll) to the page content, so the next Tab continues from there. */
  skipToContent(event: Event): void {
    event.preventDefault();
    const main = document.getElementById('main-content');
    main?.focus();
    main?.scrollIntoView();
  }
}
