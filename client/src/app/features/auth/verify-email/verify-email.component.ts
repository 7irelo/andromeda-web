import { Component, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { AuthService } from '../../../core/services/auth.service';

@Component({
    selector: 'app-verify-email',
    imports: [CommonModule, RouterLink, MatButtonModule, MatIconModule, MatProgressSpinnerModule],
    template: `
    <div class="verify-page card" role="status" aria-live="polite">
      <mat-spinner diameter="36" *ngIf="state === 'working'"></mat-spinner>
      <ng-container *ngIf="state === 'done'">
        <mat-icon class="ok">mark_email_read</mat-icon>
        <h1>Email confirmed</h1>
        <a mat-flat-button color="primary" [routerLink]="auth.isLoggedIn() ? '/feed' : '/login'">Continue</a>
      </ng-container>
      <ng-container *ngIf="state === 'failed'">
        <mat-icon class="bad">error_outline</mat-icon>
        <h1>This link didn't work</h1>
        <p class="text-secondary">It may have expired or already been used. Sign in and send a new one from Settings.</p>
        <a mat-stroked-button [routerLink]="auth.isLoggedIn() ? '/settings' : '/login'">Go to {{ auth.isLoggedIn() ? 'Settings' : 'sign in' }}</a>
      </ng-container>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    .verify-page { max-width: 420px; margin: 80px auto; padding: 32px; text-align: center; display: flex;
      flex-direction: column; align-items: center; gap: 12px; }
    mat-icon { font-size: 48px; width: 48px; height: 48px; }
    .ok { color: #2e7d32; } .bad { color: #c62828; }
  `]
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
