import { Component, ChangeDetectionStrategy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../core/services/api.service';
import { ModerationActionKind, ModerationCase } from '../../models/moderation.model';

type Filter = 'open' | 'reports' | 'auto' | 'appeals' | 'all';

/** Staff review queue: reported and auto-flagged content, appeals, and the audit trail per case. */
@Component({
    selector: 'app-moderation-console',
    imports: [CommonModule, FormsModule, MatButtonModule, MatButtonToggleModule, MatFormFieldModule, MatIconModule,
      MatInputModule, MatSnackBarModule],
    template: `
    <div class="console">
      <h1><mat-icon>gavel</mat-icon> Moderation</h1>
      <mat-button-toggle-group [value]="filter" (change)="setFilter($event.value)" aria-label="Queue">
        <mat-button-toggle value="open">Open</mat-button-toggle>
        <mat-button-toggle value="reports">Reported</mat-button-toggle>
        <mat-button-toggle value="auto">Auto-flagged</mat-button-toggle>
        <mat-button-toggle value="appeals">Appeals</mat-button-toggle>
        <mat-button-toggle value="all">History</mat-button-toggle>
      </mat-button-toggle-group>
      <p class="text-secondary" *ngIf="!loading && !cases.length">Nothing to review.</p>

      <section class="case card" *ngFor="let c of cases" [class.resolved]="c.resolved">
        <header>
          <span class="chip">{{ c.content_type }}</span>
          <span class="chip" [class.warn]="c.decision === 'remove'">{{ c.source === 'report' ? c.report_count + ' report(s)' : 'AI: ' + c.decision }}</span>
          <span class="text-secondary text-sm">by &#64;{{ c.author_username || 'deleted' }} · {{ c.created_at | date:'medium' }}</span>
        </header>
        <!-- User content is shown as text only, never as HTML. -->
        <blockquote>{{ c.content || c.snapshot || '(content deleted)' }}</blockquote>
        <p class="text-sm" *ngIf="c.content && c.snapshot && c.snapshot !== c.content">
          <strong>When flagged:</strong> {{ c.snapshot }}
        </p>
        <p class="text-sm" *ngIf="c.reason"><strong>Reason:</strong> {{ c.reason }}
          <span *ngIf="c.categories.length"> ({{ c.categories.join(', ') }})</span>
          <span *ngIf="c.model" class="text-secondary"> · {{ c.model }}, confidence {{ c.confidence | number:'1.0-2' }}</span></p>
        <ul class="reports text-sm" *ngIf="c.reports.length">
          <li *ngFor="let r of c.reports">{{ r.reason }}<span *ngIf="r.details">: {{ r.details }}</span></li>
        </ul>
        <div class="appeal" *ngIf="c.appeal">
          <strong>Appeal ({{ c.appeal.status }}):</strong> {{ c.appeal.message || 'No message.' }}
        </div>

        <div class="actions" *ngIf="!c.resolved">
          <mat-form-field appearance="outline" class="note">
            <mat-label>Note for the audit log</mat-label>
            <input matInput maxlength="500" [(ngModel)]="notes[c.id]" />
          </mat-form-field>
          <ng-container *ngIf="c.appeal?.status === 'open'; else normal">
            <button mat-flat-button color="primary" (click)="appeal(c, true)">Restore</button>
            <button mat-stroked-button (click)="appeal(c, false)">Uphold removal</button>
          </ng-container>
          <ng-template #normal>
            <button mat-stroked-button (click)="act(c, 'approve')">Approve</button>
            <button mat-flat-button color="warn" (click)="act(c, 'remove')">Remove</button>
            <button mat-stroked-button (click)="act(c, 'warn')">Warn</button>
            <button mat-stroked-button (click)="act(c, 'suspend')">Suspend {{ days }}d</button>
            <button mat-stroked-button color="warn" (click)="act(c, 'ban')">Ban</button>
            <button mat-button (click)="act(c, 'dismiss')">Dismiss</button>
          </ng-template>
        </div>
        <details *ngIf="c.actions.length">
          <summary class="text-sm">Audit log ({{ c.actions.length }})</summary>
          <ul class="text-sm"><li *ngFor="let a of c.actions">{{ a.created_at | date:'short' }} · {{ a.action }} by
            {{ a.moderator_username || a.automated_by || 'system' }}<span *ngIf="a.note">: {{ a.note }}</span></li></ul>
        </details>
      </section>
      <button mat-stroked-button *ngIf="next" (click)="load(true)">Load more</button>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    .console { max-width: 860px; margin: 0 auto; padding: 24px 16px; display: flex; flex-direction: column; gap: 12px; }
    h1 { display: flex; align-items: center; gap: 8px; font-size: 22px; margin: 0; }
    .case { padding: 16px; display: flex; flex-direction: column; gap: 8px; }
    .case.resolved { opacity: .7; }
    header { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .chip { font-size: 12px; padding: 2px 8px; border-radius: 12px; background: rgba(0,0,0,.06); text-transform: capitalize; }
    .chip.warn { background: rgba(198,40,40,.12); color: #c62828; }
    blockquote { margin: 0; padding: 8px 12px; border-left: 3px solid rgba(0,0,0,.2); white-space: pre-wrap;
      word-break: break-word; max-height: 240px; overflow: auto; }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    .note { flex: 1 1 220px; }
    .reports { margin: 0; padding-left: 20px; }
  `]
})
export class ModerationConsoleComponent implements OnInit {
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
