import { Component, ChangeDetectionStrategy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../core/services/api.service';
import { EmptyStateComponent } from '../../shared/components/states';
import { MyCase } from '../../models/moderation.model';

/** What was removed from the member's account, why, and a one-time appeal. */
@Component({
    selector: 'app-my-decisions',
    imports: [CommonModule, FormsModule, MatButtonModule, MatSnackBarModule, EmptyStateComponent],
    template: `
    <div class="page">
      <h1>Moderation decisions</h1>
      <p class="intro">Content of yours that was removed for breaking the community guidelines.
        You can ask a person to look at each decision again once.</p>
      <app-empty-state *ngIf="loaded && !cases.length" icon="task_alt" title="Nothing has been removed from your account."></app-empty-state>
      <section class="card item" *ngFor="let c of cases">
        <div class="meta">{{ c.content_type | titlecase }} · {{ c.created_at | date:'mediumDate' }}
          <span *ngIf="c.categories.length"> · {{ c.categories.join(', ') }}</span></div>
        <blockquote>{{ c.snapshot || '(no text)' }}</blockquote>
        <ng-container *ngIf="c.appeal; else canAppeal">
          <p class="status" [ngSwitch]="c.appeal.status">
            <span *ngSwitchCase="'open'">Appeal sent. A moderator will look at it.</span>
            <span *ngSwitchCase="'restored'">Your appeal was accepted and the content was restored.</span>
            <span *ngSwitchCase="'upheld'">Your appeal was reviewed and the removal stands.</span>
          </p>
        </ng-container>
        <ng-template #canAppeal>
          <div class="field">
            <label [attr.for]="'appeal-' + c.id">Why should we look again? (optional)</label>
            <textarea [id]="'appeal-' + c.id" rows="2" maxlength="1000" [(ngModel)]="messages[c.id]"></textarea>
          </div>
          <div><button mat-stroked-button (click)="appeal(c)">Appeal</button></div>
        </ng-template>
      </section>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    .page { max-width: 720px; margin: 0 auto; padding: var(--space-6) var(--space-4); display: flex; flex-direction: column;
      gap: var(--space-3); }
    .page h1 { margin: 0; font-size: var(--font-size-xl); font-weight: 600; line-height: 1.3; letter-spacing: -.01em; }
    .intro { margin: 0; font-size: var(--font-size-base); color: var(--text-secondary); }
    .item { padding: var(--space-4); display: flex; flex-direction: column; gap: var(--space-3); }
    .meta { font-size: var(--font-size-xs); color: var(--text-muted); }
    blockquote { margin: 0; padding: var(--space-2) var(--space-3); font-size: var(--font-size-base); color: var(--text-primary);
      white-space: pre-wrap; word-break: break-word; background: var(--surface-2); border-radius: var(--radius-sm); }
    .status { margin: 0; font-size: var(--font-size-sm); font-weight: 500; color: var(--text-primary); }
    .field { display: flex; flex-direction: column; gap: var(--space-1); }
    .field label { font-size: var(--font-size-sm); font-weight: 500; color: var(--text-primary); }
    .field textarea { width: 100%; padding: var(--space-2) var(--space-3); font: inherit; font-size: var(--font-size-base);
      color: var(--text-primary); resize: vertical; background: var(--surface); border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm); }
    .field textarea:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 1px var(--primary); }
    @media (max-width: 600px) {
      .page { padding: var(--space-4); --mat-button-outlined-container-height: 44px; }
      .field textarea { font-size: 16px; }
    }
  `]
})
export class MyDecisionsComponent implements OnInit {
  cases: MyCase[] = [];
  messages: Record<number, string> = {};
  loaded = false;

  constructor(private api: ApiService, private snack: MatSnackBar) {}

  ngOnInit(): void {
    this.api.getMyModerationCases().subscribe((rows) => { this.cases = rows; this.loaded = true; });
  }

  appeal(c: MyCase): void {
    this.api.appealModeration(c.id, (this.messages[c.id] ?? '').trim()).subscribe({
      next: () => (c.appeal = { id: 0, message: this.messages[c.id] ?? '', status: 'open',
                                created_at: new Date().toISOString(), decided_at: null }),
      error: (err) => this.snack.open(err?.error?.detail ?? 'Could not send the appeal', 'Dismiss', { duration: 4000 }),
    });
  }
}
