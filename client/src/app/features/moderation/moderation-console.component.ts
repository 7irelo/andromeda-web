import { Component, ChangeDetectionStrategy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../core/services/api.service';
import { EmptyStateComponent } from '../../shared/components/states';
import { ModerationActionKind, ModerationCase } from '../../models/moderation.model';

type Filter = 'open' | 'reports' | 'auto' | 'appeals' | 'all';

/** Staff review queue: reported and auto-flagged content, appeals, and the audit trail per case. */
@Component({
    selector: 'app-moderation-console',
    imports: [CommonModule, FormsModule, MatButtonModule, MatSnackBarModule, EmptyStateComponent],
    template: `
    <div class="console">
      <h1>Moderation</h1>
      <div class="filters" role="group" aria-label="Queue">
        <button type="button" *ngFor="let f of filters" class="filter" [class.active]="filter === f.value"
                [attr.aria-pressed]="filter === f.value" (click)="setFilter(f.value)">{{ f.label }}</button>
      </div>
      <app-empty-state *ngIf="!loading && !cases.length" icon="task_alt" title="Nothing to review."></app-empty-state>

      <section class="case card" *ngFor="let c of cases" [class.resolved]="c.resolved">
        <header>
          <span class="chip type">{{ c.content_type }}</span>
          <span class="chip" [class.warn]="c.decision === 'remove'">{{ c.source === 'report' ? c.report_count + ' report(s)' : 'AI: ' + c.decision }}</span>
          <span class="meta">by &#64;{{ c.author_username || 'deleted' }} · {{ c.created_at | date:'medium' }}</span>
        </header>
        <!-- User content is shown as text only, never as HTML. -->
        <blockquote>{{ c.content || c.snapshot || '(content deleted)' }}</blockquote>
        <p class="detail" *ngIf="c.content && c.snapshot && c.snapshot !== c.content">
          <strong>When flagged:</strong> {{ c.snapshot }}
        </p>
        <p class="detail" *ngIf="c.reason"><strong>Reason:</strong> {{ c.reason }}
          <span *ngIf="c.categories.length"> ({{ c.categories.join(', ') }})</span>
          <span *ngIf="c.model" class="meta"> · {{ c.model }}, confidence {{ c.confidence | number:'1.0-2' }}</span></p>
        <ul class="reports detail" *ngIf="c.reports.length">
          <li *ngFor="let r of c.reports">{{ r.reason }}<span *ngIf="r.details">: {{ r.details }}</span></li>
        </ul>
        <div class="appeal detail" *ngIf="c.appeal">
          <strong>Appeal ({{ c.appeal.status }}):</strong> {{ c.appeal.message || 'No message.' }}
        </div>

        <div class="note" *ngIf="!c.resolved">
          <label [attr.for]="'note-' + c.id">Note for the audit log</label>
          <input [id]="'note-' + c.id" maxlength="500" [(ngModel)]="notes[c.id]" />
        </div>
        <div class="actions" *ngIf="!c.resolved">
          <ng-container *ngIf="c.appeal?.status === 'open'; else normal">
            <button mat-flat-button color="primary" (click)="appeal(c, true)">Restore</button>
            <button mat-stroked-button (click)="appeal(c, false)">Uphold removal</button>
          </ng-container>
          <ng-template #normal>
            <button mat-stroked-button (click)="act(c, 'approve')">Approve</button>
            <button mat-stroked-button class="danger" (click)="act(c, 'remove')">Remove</button>
            <button mat-stroked-button (click)="act(c, 'warn')">Warn</button>
            <button mat-stroked-button (click)="act(c, 'suspend')">Suspend {{ days }}d</button>
            <button mat-stroked-button class="danger" (click)="act(c, 'ban')">Ban</button>
            <button mat-button (click)="act(c, 'dismiss')">Dismiss</button>
          </ng-template>
        </div>
        <details *ngIf="c.actions.length">
          <summary>Audit log ({{ c.actions.length }})</summary>
          <ul class="detail"><li *ngFor="let a of c.actions">{{ a.created_at | date:'short' }} · {{ a.action }} by
            {{ a.moderator_username || a.automated_by || 'system' }}<span *ngIf="a.note">: {{ a.note }}</span></li></ul>
        </details>
      </section>
      <button mat-stroked-button class="more" *ngIf="next" (click)="load(true)">Load more</button>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    .console { max-width: 860px; margin: 0 auto; padding: var(--space-6) var(--space-4); display: flex; flex-direction: column;
      gap: var(--space-3); --mat-button-text-label-text-color: var(--text-primary); }
    .console h1 { margin: 0; font-size: var(--font-size-xl); font-weight: 600; line-height: 1.3; letter-spacing: -.01em; }
    .filters { display: flex; flex-wrap: wrap; gap: var(--space-1); }
    .filter { min-height: 36px; padding: 0 var(--space-3); font: inherit; font-size: var(--font-size-sm); font-weight: 500;
      color: var(--text-secondary); background: var(--surface); border: 1px solid var(--border);
      border-radius: var(--radius-sm); cursor: pointer; }
    .filter:hover { background: var(--surface-2); }
    .filter.active { color: var(--primary); background: var(--primary-light); border-color: var(--primary); }
    .case { padding: var(--space-4); display: flex; flex-direction: column; gap: var(--space-2); font-size: var(--font-size-base); }
    .case.resolved { background: var(--surface-2); }
    .case header { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; }
    .chip { padding: 2px var(--space-2); font-size: var(--font-size-xs); font-weight: 500; color: var(--text-secondary);
      border: 1px solid var(--border); border-radius: var(--radius-sm); }
    .chip.type { text-transform: capitalize; }
    .chip.warn { color: var(--danger-text); border-color: var(--danger-text); }
    .meta { font-size: var(--font-size-xs); color: var(--text-muted); }
    blockquote { margin: 0; padding: var(--space-2) var(--space-3); color: var(--text-primary); white-space: pre-wrap;
      word-break: break-word; max-height: 240px; overflow: auto; background: var(--surface-2); border-radius: var(--radius-sm); }
    .detail { margin: 0; font-size: var(--font-size-sm); color: var(--text-secondary); }
    .detail strong { font-weight: 600; color: var(--text-primary); }
    .reports, details ul { padding-left: var(--space-5); }
    .note { display: flex; flex-direction: column; gap: var(--space-1); }
    .note label { font-size: var(--font-size-sm); font-weight: 500; color: var(--text-primary); }
    .note input { width: 100%; height: 40px; padding: 0 var(--space-3); font: inherit; font-size: var(--font-size-base);
      color: var(--text-primary); background: var(--surface); border: 1px solid var(--border-strong); border-radius: var(--radius-sm); }
    .note input:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 1px var(--primary); }
    .actions { display: flex; gap: var(--space-2); flex-wrap: wrap; align-items: center; }
    .danger { --mat-button-outlined-label-text-color: var(--danger-text); --mat-button-outlined-outline-color: var(--danger-text); }
    summary { font-size: var(--font-size-sm); color: var(--text-secondary); cursor: pointer; }
    details ul { margin-top: var(--space-2); }
    .more { align-self: center; }
    @media (max-width: 600px) {
      .console { padding: var(--space-4); --mat-button-filled-container-height: 44px; --mat-button-outlined-container-height: 44px;
        --mat-button-text-container-height: 44px; }
      .filter { min-height: 44px; }
      .note input { height: 44px; font-size: 16px; }
      summary { padding: 12px 0; }
    }
  `]
})
export class ModerationConsoleComponent implements OnInit {
  readonly filters: { value: Filter; label: string }[] = [
    { value: 'open', label: 'Open' },
    { value: 'reports', label: 'Reported' },
    { value: 'auto', label: 'Auto-flagged' },
    { value: 'appeals', label: 'Appeals' },
    { value: 'all', label: 'History' },
  ];
  cases: ModerationCase[] = [];
  filter: Filter = 'open';
  notes: Record<number, string> = {};
  days = 7;
  loading = false;
  next: string | null = null;
  private page = 1;

  constructor(private api: ApiService, private snack: MatSnackBar) {}

  ngOnInit(): void {
    this.load();
  }

  setFilter(f: Filter): void {
    this.filter = f;
    this.load();
  }

  load(more = false): void {
    this.page = more ? this.page + 1 : 1;
    const params: Record<string, string> = { page: String(this.page) };
    if (this.filter === 'reports') params['source'] = 'report';
    if (this.filter === 'auto') params['source'] = 'auto';
    if (this.filter === 'appeals') params['appeals'] = 'true';
    if (this.filter === 'all') params['all'] = 'true';
    this.loading = true;
    this.api.getModerationQueue(params).subscribe({
      next: (r) => {
        this.cases = more ? [...this.cases, ...r.results] : r.results;
        this.next = r.next;
        this.loading = false;
      },
      error: () => (this.loading = false),
    });
  }

  private replace(updated: ModerationCase): void {
    this.cases = this.cases.map((c) => (c.id === updated.id ? updated : c));
  }

  private failed(err: { error?: { detail?: string; days?: string[] } }): void {
    this.snack.open(err?.error?.detail ?? err?.error?.days?.[0] ?? 'That action failed', 'Dismiss', { duration: 4000 });
  }

  act(c: ModerationCase, action: ModerationActionKind): void {
    this.api.resolveModerationCase(c.id, action, this.notes[c.id] ?? '', action === 'suspend' ? this.days : undefined)
      .subscribe({ next: (u) => this.replace(u), error: (e) => this.failed(e) });
  }

  appeal(c: ModerationCase, restore: boolean): void {
    this.api.decideAppeal(c.id, restore, this.notes[c.id] ?? '')
      .subscribe({ next: (u) => this.replace(u), error: (e) => this.failed(e) });
  }
}
