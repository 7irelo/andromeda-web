import { ChangeDetectionStrategy, Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../core/services/api.service';
import { AccessToken, TokenScope } from '../../models/assistant.model';

/** Personal access tokens for MCP clients. The token is shown once, right after it's created. */
@Component({
  selector: 'app-token-settings',
  imports: [CommonModule, FormsModule, MatButtonModule, MatCheckboxModule, MatFormFieldModule, MatIconModule,
    MatInputModule, MatSelectModule, MatSnackBarModule],
  changeDetection: ChangeDetectionStrategy.Eager,
  template: `
  <section class="settings-section card">
    <h2><mat-icon>key</mat-icon> Access tokens</h2>
    <p class="text-secondary">Let an AI app that supports MCP use the assistant's tools as you, at
      <code>/api/mcp/</code>. Tokens can read what you can see. With "Propose", they can also draft posts and
      messages, which wait for your approval in the assistant panel.</p>

    <div class="new-token" *ngIf="created">
      <div class="font-semibold">Copy your new token now. You won't see it again.</div>
      <div class="token-row">
        <code class="token">{{ created }}</code>
        <button mat-stroked-button (click)="copy()"><mat-icon>content_copy</mat-icon> Copy</button>
        <button mat-button (click)="created = ''">Done</button>
      </div>
    </div>

    <form class="create" (ngSubmit)="create()" *ngIf="!created">
      <mat-form-field appearance="outline">
        <mat-label>Name</mat-label>
        <input matInput [(ngModel)]="name" name="name" maxlength="60" required placeholder="e.g. Laptop">
      </mat-form-field>
      <mat-form-field appearance="outline">
        <mat-label>Expires after</mat-label>
        <mat-select [(ngModel)]="days" name="days">
          <mat-option *ngFor="let d of dayOptions" [value]="d">{{ d }} days</mat-option>
        </mat-select>
      </mat-form-field>
      <div class="scopes">
        <mat-checkbox [checked]="true" disabled>Read</mat-checkbox>
        <mat-checkbox [(ngModel)]="propose" name="propose">Propose posts and messages</mat-checkbox>
      </div>
      <mat-form-field appearance="outline">
        <mat-label>Your password</mat-label>
        <input matInput type="password" [(ngModel)]="password" name="password" required
               autocomplete="current-password">
      </mat-form-field>
      <button mat-flat-button color="primary" type="submit" [disabled]="!name.trim() || !password || saving">
        Create token</button>
    </form>

    <div class="token-item" *ngFor="let t of tokens">
      <mat-icon>vpn_key</mat-icon>
      <div class="grow">
        <div class="font-semibold">{{ t.name }} <code>{{ t.prefix }}…</code></div>
        <div class="text-secondary text-sm">{{ t.scopes.join(' + ') }} · expires {{ t.expires_at | date:'mediumDate' }}
          · {{ t.last_used_at ? 'last used ' + (t.last_used_at | date:'medium') : 'never used' }}</div>
      </div>
      <button mat-stroked-button color="warn" (click)="revoke(t)">Revoke</button>
    </div>
  </section>
  `,
  styles: [`
    .settings-section { padding: 24px; margin-bottom: 16px; }
    .create { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
    .scopes { display: flex; gap: 12px; flex-wrap: wrap; }
    .new-token { background: var(--primary-light); padding: 12px; border-radius: var(--border-radius-sm); }
    .token-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 6px; }
    .token { word-break: break-all; user-select: all; }
    .token-item { display: flex; align-items: center; gap: 12px; padding: 8px 0; border-top: 1px solid var(--border); }
    .grow { flex: 1; }
  `],
})
export class TokenSettingsComponent implements OnInit {
  tokens: AccessToken[] = [];
  name = '';
  days = 30;
  propose = false;
  password = '';
  saving = false;
  created = '';
  readonly dayOptions = [7, 30, 60, 90];

  constructor(private api: ApiService, private snack: MatSnackBar) {}

  ngOnInit(): void {
    this.load();
  }

  private load(): void {
    this.api.getAccessTokens().subscribe((rows) => (this.tokens = rows));
  }

  create(): void {
    const scopes: TokenScope[] = this.propose ? ['read', 'propose'] : ['read'];
    this.saving = true;
    this.api.createAccessToken(this.name.trim(), scopes, this.days, this.password).subscribe({
      next: (t) => {
        this.created = t.token;
        this.saving = false;
        this.name = '';
        this.password = '';
        this.propose = false;
        this.load();
      },
      error: (err) => {
        this.saving = false;
        this.snack.open(err?.error?.password?.[0] ?? err?.error?.detail?.[0] ?? err?.error?.detail
          ?? 'Could not create the token', 'Dismiss', { duration: 4000 });
      },
    });
  }

  copy(): void {
    navigator.clipboard?.writeText(this.created).then(
      () => this.snack.open('Token copied', undefined, { duration: 2000 }), () => {});
  }

  revoke(t: AccessToken): void {
    if (!confirm(`Revoke "${t.name}"? Apps using it stop working immediately.`)) return;
    this.api.revokeAccessToken(t.id).subscribe(() => this.load());
  }
}
