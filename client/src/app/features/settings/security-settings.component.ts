import { Component, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { AuthService } from '../../core/services/auth.service';
import { ApiService } from '../../core/services/api.service';
import { DeviceSession, MfaSetup, MfaStatus } from '../../models/user.model';

/** Email verification, two-factor sign-in, signed-in devices and the AI opt-out. */
@Component({
    selector: 'app-security-settings',
    imports: [CommonModule, FormsModule, MatButtonModule, MatFormFieldModule, MatIconModule, MatInputModule,
      MatSlideToggleModule, MatSnackBarModule],
    template: `
    <section class="settings-section card" *ngIf="auth.currentUser as me">
      <h2><mat-icon>verified_user</mat-icon> Account security</h2>

      <div class="row" *ngIf="!me.email_verified">
        <mat-icon class="warn">mark_email_unread</mat-icon>
        <div class="grow">
          <div class="font-semibold">Confirm your email</div>
          <div class="text-secondary text-sm">We sent a link to {{ me.email }}. Confirming lets you recover your account.</div>
        </div>
        <button mat-stroked-button (click)="resend()" [disabled]="resent">{{ resent ? 'Sent' : 'Resend link' }}</button>
      </div>

      <h3>Two-factor sign-in</h3>
      <ng-container *ngIf="mfa">
        <ng-container *ngIf="mfa.enabled && !recoveryCodes">
          <p class="text-secondary">On. You have {{ mfa.recovery_codes_left }} recovery codes left.</p>
          <div class="inline-form">
            <mat-form-field appearance="outline"><mat-label>Password</mat-label>
              <input matInput type="password" autocomplete="current-password" [(ngModel)]="password" /></mat-form-field>
            <mat-form-field appearance="outline"><mat-label>Code</mat-label>
              <input matInput autocomplete="one-time-code" inputmode="numeric" maxlength="12" [(ngModel)]="code" /></mat-form-field>
            <button mat-stroked-button color="warn" (click)="disable()" [disabled]="!password || !code">Turn off</button>
          </div>
        </ng-container>

        <ng-container *ngIf="!mfa.enabled && !setup">
          <p class="text-secondary">Add a code from an authenticator app to every sign-in.</p>
          <div class="inline-form">
            <mat-form-field appearance="outline"><mat-label>Password</mat-label>
              <input matInput type="password" autocomplete="current-password" [(ngModel)]="password" /></mat-form-field>
            <button mat-flat-button color="primary" (click)="startSetup()" [disabled]="!password">Set up</button>
          </div>
        </ng-container>

        <div *ngIf="setup" class="setup">
          <img [src]="setup.qr_png" width="180" height="180" alt="QR code for your authenticator app" />
          <div>
            <p>Scan the code with your authenticator app, or enter this key:</p>
            <code class="secret">{{ setup.secret }}</code>
            <div class="inline-form">
              <mat-form-field appearance="outline"><mat-label>6-digit code</mat-label>
                <input matInput autocomplete="one-time-code" inputmode="numeric" maxlength="6" [(ngModel)]="code" /></mat-form-field>
              <button mat-flat-button color="primary" (click)="enable()" [disabled]="code.length !== 6">Turn on</button>
            </div>
          </div>
        </div>

        <div *ngIf="recoveryCodes" class="codes" role="status">
          <p class="font-semibold">Save these recovery codes somewhere safe. Each works once, and they won't be shown again.</p>
          <ul><li *ngFor="let c of recoveryCodes"><code>{{ c }}</code></li></ul>
          <button mat-stroked-button (click)="recoveryCodes = null">I've saved them</button>
        </div>
      </ng-container>

      <h3>Where you're signed in</h3>
      <div class="row" *ngFor="let s of sessions">
        <mat-icon>{{ deviceIcon(s.user_agent) }}</mat-icon>
        <div class="grow">
          <div class="font-semibold">{{ deviceName(s.user_agent) }} <span class="current" *ngIf="s.current">This device</span></div>
          <div class="text-secondary text-sm">Last active {{ s.last_seen_at | date:'medium' }}<span *ngIf="s.network"> · {{ s.network }}</span></div>
        </div>
        <button mat-button *ngIf="!s.current" (click)="revoke(s)">Sign out</button>
      </div>

      <h3>AI features</h3>
      <mat-slide-toggle [checked]="!me.ai_opt_out" (change)="setAiOptOut(!$event.checked)">
        Use AI features (smart search, Ask Andromeda, summaries)
      </mat-slide-toggle>
      <p class="text-secondary text-sm">When off, your posts, listings and videos aren't indexed for semantic search or
        used to answer anyone's questions, and AI features are turned off for you. Safety checks on new content still run.</p>
    </section>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    .settings-section { padding: 24px; margin-bottom: 16px; }
    h3 { font-size: 15px; margin: 20px 0 8px; }
    .row { display: flex; align-items: center; gap: 12px; padding: 8px 0; }
    .grow { flex: 1; }
    .warn { color: var(--warn, #c62828); }
    .inline-form { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
    .setup { display: flex; gap: 16px; flex-wrap: wrap; align-items: flex-start; }
    .secret { display: inline-block; padding: 4px 8px; letter-spacing: 2px; word-break: break-all; }
    .codes ul { columns: 2; padding-left: 20px; }
    .current { font-size: 12px; margin-left: 8px; opacity: .7; }
  `]
})
export class SecuritySettingsComponent implements OnInit {
  mfa: MfaStatus | null = null;
  setup: MfaSetup | null = null;
  recoveryCodes: string[] | null = null;
  sessions: DeviceSession[] = [];
  password = '';
  code = '';
  resent = false;

  constructor(public auth: AuthService, private api: ApiService, private snack: MatSnackBar) {}

  ngOnInit(): void {
    this.auth.getMfaStatus().subscribe((s) => (this.mfa = s));
    this.loadSessions();
  }

  private loadSessions(): void {
    this.auth.getSessions().subscribe((rows) => (this.sessions = rows));
  }

  private fail(err: { error?: Record<string, unknown> }, fallback: string): void {
    const e = err?.error ?? {};
    const pick = (k: string) => (Array.isArray(e[k]) ? (e[k] as string[])[0] : (e[k] as string | undefined));
    this.snack.open(pick('code') ?? pick('password') ?? pick('detail') ?? fallback, 'Dismiss', { duration: 4000 });
  }

  resend(): void {
    this.auth.resendVerification().subscribe(() => (this.resent = true));
  }

  startSetup(): void {
    this.auth.startMfaSetup(this.password).subscribe({
      next: (s) => { this.setup = s; this.password = ''; this.code = ''; },
      error: (err) => this.fail(err, 'Could not start setup'),
    });
  }

  enable(): void {
    this.auth.enableMfa(this.code).subscribe({
      next: (r) => {
        this.recoveryCodes = r.recovery_codes;
        this.setup = null;
        this.code = '';
        this.mfa = { enabled: true, recovery_codes_left: r.recovery_codes.length };
        this.loadSessions();
      },
      error: (err) => this.fail(err, 'That code is not valid'),
    });
  }

  disable(): void {
    this.auth.disableMfa(this.password, this.code).subscribe({
      next: () => { this.mfa = { enabled: false, recovery_codes_left: 0 }; this.password = ''; this.code = ''; },
      error: (err) => this.fail(err, 'Could not turn off two-factor sign-in'),
    });
  }

  revoke(s: DeviceSession): void {
    this.auth.revokeSession(s.id).subscribe(() => (this.sessions = this.sessions.filter((x) => x.id !== s.id)));
  }

  setAiOptOut(optOut: boolean): void {
    this.api.updateProfile({ ai_opt_out: optOut }).subscribe({
      next: () => this.auth.fetchMe().subscribe(),
      error: () => this.snack.open('Could not save that setting', 'Dismiss', { duration: 3000 }),
    });
  }

  deviceName(ua: string): string {
    const browser = /Edg\//.test(ua) ? 'Edge' : /Firefox\//.test(ua) ? 'Firefox' : /Chrome\//.test(ua) ? 'Chrome'
      : /Safari\//.test(ua) ? 'Safari' : 'Browser';
    const os = /Windows/.test(ua) ? 'Windows' : /Android/.test(ua) ? 'Android' : /iPhone|iPad/.test(ua) ? 'iOS'
      : /Mac OS X/.test(ua) ? 'macOS' : /Linux/.test(ua) ? 'Linux' : '';
    return os ? `${browser} on ${os}` : browser;
  }

  deviceIcon(ua: string): string {
    return /Android|iPhone|iPad|Mobile/.test(ua) ? 'smartphone' : 'computer';
  }
}
