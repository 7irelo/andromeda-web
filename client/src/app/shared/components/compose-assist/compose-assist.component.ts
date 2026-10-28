import { ChangeDetectionStrategy, Component, EventEmitter, Input, OnDestroy, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { Subscription } from 'rxjs';
import { ApiService } from '../../../core/services/api.service';
import { AuthService } from '../../../core/services/auth.service';
import {
  COMPOSE_LANGUAGES, COMPOSE_MAX_CHARS, COMPOSE_TONES, ComposeAction, ComposeLanguage,
} from '../../../models/assist.model';

/**
 * "✨ Help me write": rewrite a draft in another tone, fix its grammar, shorten
 * it or translate it. The suggestion is shown next to the draft with Accept /
 * Discard; it never replaces the author's text by itself. Hidden when the user
 * has turned AI off.
 */
@Component({
  selector: 'app-compose-assist',
  imports: [CommonModule, MatButtonModule, MatIconModule, MatMenuModule, MatProgressSpinnerModule],
  changeDetection: ChangeDetectionStrategy.Eager,
  template: `
    <ng-container *ngIf="enabled">
      <button mat-button type="button" class="assist-btn" [matMenuTriggerFor]="assistMenu"
              [disabled]="!canAssist || loading" aria-label="Help me write">
        <mat-spinner *ngIf="loading" diameter="16"></mat-spinner>
        <span *ngIf="!loading" aria-hidden="true">✨</span>
        {{ loading ? 'Writing…' : 'Help me write' }}
      </button>
      <mat-menu #assistMenu="matMenu">
        <button mat-menu-item *ngFor="let t of tones" (click)="run(t.action)">
          <mat-icon>{{ t.icon }}</mat-icon> {{ t.label }}
        </button>
        <button mat-menu-item [matMenuTriggerFor]="langMenu"><mat-icon>translate</mat-icon> Translate</button>
      </mat-menu>
      <mat-menu #langMenu="matMenu">
        <button mat-menu-item *ngFor="let l of languages" (click)="run('translate', l.code)">{{ l.label }}</button>
      </mat-menu>

      <p class="assist-error text-xs" *ngIf="error" role="alert">{{ error }}</p>

      <div class="assist-suggestion" *ngIf="suggestion !== null" role="region" aria-label="Suggested text">
        <div class="assist-label text-xs"><mat-icon>auto_awesome</mat-icon> Suggestion: check it before you use it</div>
        <p class="assist-text">{{ suggestion }}</p>
        <p class="text-xs text-secondary" *ngIf="truncated">The suggestion was cut short.</p>
        <div class="assist-actions">
          <button mat-stroked-button type="button" (click)="discard()">Discard</button>
          <button mat-flat-button color="primary" type="button" (click)="accept()">Accept</button>
        </div>
      </div>
    </ng-container>
  `,
  styles: [`
    :host { display: block; }
    .assist-btn { border-radius: 8px; display: inline-flex; align-items: center; gap: 6px; }
    .assist-error { color: var(--danger); margin: 4px 0 0; }
    .assist-suggestion {
      margin-top: 8px; padding: 10px 12px; border: 1px dashed var(--primary); border-radius: 10px;
      background: var(--primary-light);
    }
    .assist-label { display: flex; align-items: center; gap: 4px; color: var(--primary); font-weight: 600; }
    .assist-label mat-icon { font-size: 14px; width: 14px; height: 14px; }
    .assist-text { white-space: pre-wrap; word-break: break-word; margin: 6px 0; font-size: 14px; }
    .assist-actions { display: flex; justify-content: flex-end; gap: 8px; }
  `],
})
export class ComposeAssistComponent implements OnDestroy {
  /** The author's current draft. */
  @Input() text = '';
  @Input() kind: 'post' | 'listing' = 'post';
  /** Emits the suggestion only when the author accepts it. */
  @Output() accepted = new EventEmitter<string>();

  readonly tones = COMPOSE_TONES;
  readonly languages = COMPOSE_LANGUAGES;

  loading = false;
  error = '';
  suggestion: string | null = null;
  truncated = false;
  private sub?: Subscription;

  constructor(private api: ApiService, private auth: AuthService) {}

  get enabled(): boolean {
    const me = this.auth.currentUser;
    return !!me && !me.ai_opt_out;
  }

  get canAssist(): boolean {
    const t = (this.text ?? '').trim();
    return t.length > 0 && t.length <= COMPOSE_MAX_CHARS;
  }

  run(action: ComposeAction, language?: ComposeLanguage): void {
    if (!this.canAssist) return;
    this.sub?.unsubscribe();
    this.loading = true;
    this.error = '';
    this.suggestion = null;
    this.sub = this.api.composeAssist({ text: this.text.trim(), action, language, kind: this.kind }).subscribe({
      next: (res) => {
        this.loading = false;
        this.suggestion = res.text;
        this.truncated = res.truncated;
      },
      error: (err: HttpErrorResponse) => {
        this.loading = false;
        this.error = err?.status === 429
          ? (err.error?.detail ?? "You've used your AI allowance for now.")
          : (typeof err?.error?.detail === 'string' ? err.error.detail : 'Writing help is not available right now.');
      },
    });
  }

  accept(): void {
    if (this.suggestion === null) return;
    this.accepted.emit(this.suggestion);
    this.suggestion = null;
  }

  discard(): void {
    this.suggestion = null;
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }
}
