import {
  ChangeDetectionStrategy, Component, ElementRef, EventEmitter, OnDestroy, OnInit, Output, ViewChild,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Subscription } from 'rxjs';
import { ApiService } from '../../core/services/api.service';
import { WebSocketService } from '../../core/services/websocket.service';
import { AssistantProposal, AssistantRun } from '../../models/assistant.model';
import { isActive, safeCitationUrl, stepLabel } from './assistant.util';

const POLL_MS = 3000;
const TYPE_ICONS: Record<string, string> = {
  posts: 'article', listings: 'storefront', groups: 'group', pages: 'auto_stories', videos: 'play_circle',
};

/**
 * The assistant side panel: the conversation, live progress, cited results and
 * confirmation cards. Nothing the assistant proposes is posted or sent until
 * Approve is clicked here, and the card shows exactly what and to whom.
 */
@Component({
  selector: 'app-assistant-panel',
  imports: [CommonModule, FormsModule, RouterLink, MatButtonModule, MatIconModule, MatProgressSpinnerModule,
    MatTooltipModule],
  changeDetection: ChangeDetectionStrategy.Eager,
  template: `
  <aside class="assistant-panel" role="dialog" aria-label="Andromeda Assistant">
    <header>
      <mat-icon class="spark">auto_awesome</mat-icon>
      <h2>Assistant</h2>
      <button mat-icon-button (click)="closed.emit()" aria-label="Close assistant"><mat-icon>close</mat-icon></button>
    </header>

    <div class="conversation" #scroller>
      <p class="hint" *ngIf="!runs.length && !external.length">
        Ask about posts, listings, groups or your chats, or ask for a draft. Anything that posts or sends a
        message waits for your approval.
      </p>

      <section class="external" *ngIf="external.length">
        <h3><mat-icon>extension</mat-icon> From your connected apps</h3>
        <ng-container *ngFor="let p of external">
          <ng-container *ngTemplateOutlet="card; context: { $implicit: p }"></ng-container>
        </ng-container>
      </section>

      <div class="exchange" *ngFor="let run of runs; trackBy: trackRun">
        <div class="bubble mine">{{ run.request_text }}</div>

        <div class="progress" *ngIf="active(run)">
          <mat-spinner diameter="16"></mat-spinner>
          <span>{{ lastStep(run) }}</span>
        </div>

        <div class="bubble theirs" *ngIf="run.answer">{{ run.answer }}</div>
        <div class="bubble error" *ngIf="run.status === 'failed'">{{ run.error || 'Something went wrong.' }}</div>

        <div class="citations" *ngIf="run.citations.length">
          <ng-container *ngFor="let c of run.citations">
            <a *ngIf="link(c.url) as url" [routerLink]="url" class="chip" (click)="closed.emit()">
              <mat-icon>{{ icon(c.type) }}</mat-icon>{{ c.title }}
            </a>
          </ng-container>
        </div>

        <ng-container *ngFor="let p of run.proposals">
          <ng-container *ngTemplateOutlet="card; context: { $implicit: p }"></ng-container>
        </ng-container>
      </div>
    </div>

    <form class="composer" (ngSubmit)="send()">
      <textarea [(ngModel)]="draft" name="draft" rows="2" maxlength="2000" placeholder="Ask the assistant…"
                (keydown.enter)="onEnter($event)" [disabled]="sending" aria-label="Message the assistant"></textarea>
      <button mat-icon-button color="primary" type="submit" [disabled]="!draft.trim() || sending"
              aria-label="Send"><mat-icon>send</mat-icon></button>
    </form>
    <p class="error-line" *ngIf="errorText">{{ errorText }}</p>
  </aside>

  <ng-template #card let-p>
    <div class="proposal" [class.decided]="p.status !== 'pending'">
      <div class="proposal-head">
        <mat-icon>{{ p.preview.action === 'post' ? 'post_add' : 'send' }}</mat-icon>
        <span *ngIf="p.preview.action === 'post'">Post to <b>{{ p.preview.audience }}</b></span>
        <span *ngIf="p.preview.action === 'message'">Message to
          <b>{{ recipients(p) }}</b><span *ngIf="p.preview.room?.name"> in {{ p.preview.room?.name }}</span></span>
      </div>
      <div class="proposal-text">{{ p.preview.text }}</div>
      <div class="links-warning" *ngIf="p.preview.links?.length">
        <mat-icon>link</mat-icon> Contains links: {{ p.preview.links.join(', ') }}
      </div>
      <div class="proposal-actions" *ngIf="p.status === 'pending' && !expired(p)">
        <span class="expires">Expires {{ p.expires_at | date:'shortTime' }}</span>
        <button mat-stroked-button (click)="decide(p, false)" [disabled]="busy.has(p.id)">Reject</button>
        <button mat-flat-button color="primary" (click)="decide(p, true)" [disabled]="busy.has(p.id)">
          {{ p.preview.action === 'post' ? 'Approve and post' : 'Approve and send' }}
        </button>
      </div>
      <div class="proposal-status" *ngIf="p.status !== 'pending' || expired(p)">
        <ng-container [ngSwitch]="expired(p) && p.status === 'pending' ? 'expired' : p.status">
          <span *ngSwitchCase="'approved'"><mat-icon>check_circle</mat-icon> Done
            <a *ngIf="link(p.result?.url) as url" [routerLink]="url" (click)="closed.emit()">View post</a></span>
          <span *ngSwitchCase="'rejected'"><mat-icon>block</mat-icon> Rejected</span>
          <span *ngSwitchCase="'expired'"><mat-icon>schedule</mat-icon> Expired</span>
          <span *ngSwitchCase="'failed'"><mat-icon>error</mat-icon> {{ p.error || 'Could not be done' }}</span>
        </ng-container>
      </div>
    </div>
  </ng-template>
  `,
  styles: [`
    :host { position: fixed; top: var(--header-height, 60px); right: 0; bottom: 0; z-index: 99;
      width: min(420px, 100vw); }
    .assistant-panel { height: 100%; display: flex; flex-direction: column; background: var(--surface);
      border-left: 1px solid var(--border); box-shadow: var(--shadow-lg); }
    header { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid var(--border); }
    header h2 { flex: 1; margin: 0; font-size: 17px; }
    .spark { color: var(--primary); }
    .conversation { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 12px; }
    .hint { color: var(--text-secondary); font-size: 14px; }
    .exchange { display: flex; flex-direction: column; gap: 6px; }
    .bubble { padding: 8px 12px; border-radius: var(--border-radius); white-space: pre-wrap; word-break: break-word;
      font-size: 14px; max-width: 90%; }
    .mine { align-self: flex-end; background: var(--primary); color: #fff; }
    .theirs { align-self: flex-start; background: var(--surface-2); border: 1px solid var(--border); }
    .error { align-self: flex-start; background: rgba(239, 68, 68, .1); color: var(--danger); }
    .progress { display: flex; align-items: center; gap: 8px; color: var(--text-secondary); font-size: 13px; }
    .citations { display: flex; flex-wrap: wrap; gap: 6px; }
    .chip { display: inline-flex; align-items: center; gap: 4px; padding: 2px 10px; border-radius: 16px;
      background: var(--primary-light); color: var(--primary); font-size: 13px; text-decoration: none; }
    .chip mat-icon { font-size: 16px; width: 16px; height: 16px; }
    .proposal { border: 1px solid var(--primary); border-radius: var(--border-radius); padding: 10px;
      background: var(--surface); display: flex; flex-direction: column; gap: 8px; }
    .proposal.decided { border-color: var(--border); opacity: .85; }
    .proposal-head { display: flex; align-items: center; gap: 6px; font-size: 14px; }
    .proposal-text { white-space: pre-wrap; word-break: break-word; background: var(--surface-2);
      border-radius: var(--border-radius-sm); padding: 8px; font-size: 14px; }
    .links-warning { display: flex; align-items: center; gap: 4px; color: var(--warning); font-size: 13px;
      word-break: break-all; }
    .proposal-actions { display: flex; align-items: center; gap: 8px; justify-content: flex-end; }
    .expires { flex: 1; color: var(--text-muted); font-size: 12px; }
    .proposal-status span { display: inline-flex; align-items: center; gap: 4px; font-size: 13px;
      color: var(--text-secondary); }
    .external h3 { display: flex; align-items: center; gap: 6px; font-size: 14px; margin: 0 0 6px; }
    .composer { display: flex; align-items: flex-end; gap: 6px; padding: 8px 12px; border-top: 1px solid var(--border); }
    .composer textarea { flex: 1; resize: none; border: 1px solid var(--border); border-radius: var(--border-radius-sm);
      padding: 8px; font: inherit; background: var(--bg); color: var(--text-primary); }
    .error-line { color: var(--danger); font-size: 13px; margin: 0 12px 8px; }
  `],
})
export class AssistantPanelComponent implements OnInit, OnDestroy {
  @Output() closed = new EventEmitter<void>();
  @ViewChild('scroller') scroller?: ElementRef<HTMLElement>;

  runs: AssistantRun[] = [];
  external: AssistantProposal[] = [];
  draft = '';
  sending = false;
  errorText = '';
  busy = new Set<number>();
  private poll: ReturnType<typeof setInterval> | null = null;
  private sub?: Subscription;

  constructor(private api: ApiService, private ws: WebSocketService) {}

  ngOnInit(): void {
    this.api.getAssistantRuns().subscribe((runs) => {
      this.runs = [...runs].reverse();
      this.syncPolling();
      this.scrollDown();
    });
    this.loadExternal();
    this.sub = this.ws.assistantEvent$.subscribe((e) => {
      if (this.runs.some((r) => r.id === e.run_id)) this.refresh(e.run_id);
    });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
    if (this.poll) clearInterval(this.poll);
  }

  trackRun = (_: number, run: AssistantRun) => run.id;
  active = isActive;
  link = safeCitationUrl;

  lastStep(run: AssistantRun): string {
    const step = run.steps[run.steps.length - 1];
    return step ? stepLabel(step) : 'Starting';
  }

  icon(type: string): string {
    return TYPE_ICONS[type] ?? 'link';
  }

  recipients(p: AssistantProposal): string {
    return (p.preview.to ?? []).map((u) => `${u.name} (@${u.username})`).join(', ') || 'this chat';
  }

  expired(p: AssistantProposal): boolean {
    return new Date(p.expires_at).getTime() <= Date.now();
  }

  onEnter(event: Event): void {
    const e = event as KeyboardEvent;
    if (!e.shiftKey) {
      e.preventDefault();
      this.send();
    }
  }

  send(): void {
    const text = this.draft.trim();
    if (!text || this.sending) return;
    const previous = [...this.runs].reverse().find((r) => r.status === 'done');
    this.sending = true;
    this.errorText = '';
    this.api.startAssistantRun(text, previous?.id ?? null).subscribe({
      next: (run) => {
        this.runs = [...this.runs, run];
        this.draft = '';
        this.sending = false;
        this.syncPolling();
        this.scrollDown();
      },
      error: (err) => {
        this.sending = false;
        this.errorText = err?.error?.detail ?? err?.error?.request?.[0] ?? 'The assistant is not available right now.';
      },
    });
  }

  decide(p: AssistantProposal, approve: boolean): void {
    this.busy.add(p.id);
    const call = approve ? this.api.approveProposal(p.id) : this.api.rejectProposal(p.id);
    call.subscribe({
      next: (updated) => this.applyDecision(updated),
      error: (err) => {
        this.busy.delete(p.id);
        this.errorText = err?.error?.detail ?? 'That did not work. Try again.';
        if (p.run) this.refresh(p.run);
        this.loadExternal();
      },
    });
  }

  private applyDecision(updated: AssistantProposal): void {
    this.busy.delete(updated.id);
    this.external = this.external.filter((x) => x.id !== updated.id);
    if (updated.run) {
      this.runs = this.runs.map((r) => r.id !== updated.run ? r :
        { ...r, proposals: r.proposals.map((x) => x.id === updated.id ? updated : x) });
      this.refresh(updated.run);
    }
  }

  private refresh(runId: number): void {
    this.api.getAssistantRun(runId).subscribe((run) => {
      this.runs = this.runs.map((r) => (r.id === run.id ? run : r));
      this.syncPolling();
      this.scrollDown();
    });
  }

  private loadExternal(): void {
    this.api.getAssistantProposals('pending').subscribe({
      next: (rows) => (this.external = rows.filter((p) => p.run === null)),
      error: () => {},
    });
  }

  /** The socket pushes progress; polling is the fallback while a run is working. */
  private syncPolling(): void {
    const working = this.runs.filter(isActive);
    if (working.length && !this.poll) {
      this.poll = setInterval(() => this.runs.filter(isActive).forEach((r) => this.refresh(r.id)), POLL_MS);
    } else if (!working.length && this.poll) {
      clearInterval(this.poll);
      this.poll = null;
    }
  }

  private scrollDown(): void {
    setTimeout(() => {
      const el = this.scroller?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }
}
