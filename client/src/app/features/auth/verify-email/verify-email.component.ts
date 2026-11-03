import { Component, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { AuthService } from '../../../core/services/auth.service';

@Component({
    selector: 'app-verify-email',
    imports: [CommonModule, RouterLink, MatIconModule, MatProgressSpinnerModule],
    template: `
    <div class="auth-page">
      <div class="stars" aria-hidden="true"></div>
      <div class="planet" aria-hidden="true"></div>

      <header class="auth-header">
        <a class="brand brand-link" routerLink="/">
          <svg class="brand-mark" viewBox="0 0 32 28" width="30" height="26" aria-hidden="true">
            <defs>
              <linearGradient id="brand-gradient" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stop-color="#ffffff" />
                <stop offset="1" stop-color="#7c8cff" />
              </linearGradient>
            </defs>
            <path d="M16 0 32 28H24.5L16 12.6 9.6 24 20 24 22.2 28H0L16 0Z" />
          </svg>
          ANDROMEDA
        </a>
      </header>

      <div class="auth-main single">
        <section class="auth-card" role="status" aria-live="polite">
          <div class="verify-working" *ngIf="state === 'working'"><mat-spinner diameter="36"></mat-spinner></div>
          <ng-container *ngIf="state === 'done'">
            <mat-icon class="notice-icon" aria-hidden="true">mark_email_read</mat-icon>
            <h1 class="flush" i18n="@@verify.done">Email confirmed</h1>
            <a class="submit-btn" [routerLink]="auth.isLoggedIn() ? '/feed' : '/login'" i18n="@@onboarding.continue">Continue</a>
          </ng-container>
          <ng-container *ngIf="state === 'failed'">
            <mat-icon class="notice-icon bad" aria-hidden="true">error_outline</mat-icon>
            <h1 i18n="@@verify.failed">This link didn't work</h1>
            <p class="auth-hint flush" i18n="@@verify.failedHint">It may have expired or already been used. Sign in and send a new one from Settings.</p>
            @if (auth.isLoggedIn()) {
              <a class="secondary-btn" routerLink="/settings" i18n="@@verify.toSettings">Go to Settings</a>
            } @else {
              <a class="secondary-btn" routerLink="/login" i18n="@@verify.toSignIn">Go to sign in</a>
            }
          </ng-container>
        </section>
      </div>

      <footer class="auth-footer">
        <a routerLink="/privacy" i18n="@@login.privacy">Privacy</a>
        <a routerLink="/terms" i18n="@@login.terms">Terms</a>
      </footer>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styleUrls: ['../login/login.component.scss', '../password-reset/password-reset.scss']
})
export class VerifyEmailComponent implements OnInit {
  state: 'working' | 'done' | 'failed' = 'working';

  constructor(private route: ActivatedRoute, private router: Router, public auth: AuthService) {}

  ngOnInit(): void {
    const token = this.route.snapshot.queryParamMap.get('token') ?? '';
    // Drop the token from the address bar and history straight away.
    this.router.navigate([], { queryParams: {}, replaceUrl: true });
    if (!token) {
      this.state = 'failed';
      return;
    }
    this.auth.verifyEmail(token).subscribe({
      next: () => {
        this.state = 'done';
        if (this.auth.isLoggedIn()) {
          this.auth.fetchMe().subscribe();
        }
      },
      error: () => (this.state = 'failed'),
    });
  }
}
