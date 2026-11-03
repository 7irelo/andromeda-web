import {
  ChangeDetectionStrategy, Component, ElementRef, EventEmitter, OnDestroy, OnInit, Output, ViewChild,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { VoiceChatComponent } from './voice-chat.component';
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
  imports: [CommonModule, FormsModule, RouterLink, VoiceChatComponent, MatButtonModule, MatIconModule, MatProgressSpinnerModule,
    MatTooltipModule],
  changeDetection: ChangeDetectionStrategy.Eager,
  template: `
  <aside class="assistant-panel" role="dialog" aria-label="Andromeda Assistant">
    <header>
      <mat-icon class="spark" aria-hidden="true">auto_awesome</mat-icon>
      <h2>Assistant</h2>
      <button mat-icon-button (click)="closed.emit()" aria-label="Close assistant"><mat-icon>close</mat-icon></button>
    </header>
    <app-voice-chat></app-voice-chat>

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
    :host { position: fixed; top: var(--header-height, 60px); right: 0; bottom: var(--bottom-nav-height, 0px); z-index: 99;
      width: min(400px, 100vw); }
    .assistant-panel { height: 100%; display: flex; flex-direction: column; background: var(--surface);
      border-left: 1px solid var(--border); font-size: var(--font-size-base); }
    header { display: flex; align-items: center; gap: var(--space-2); padding: var(--space-1) var(--space-2) var(--space-1) var(--space-4);
      border-bottom: 1px solid var(--border); }
    header h2 { flex: 1; margin: 0; font-size: var(--font-size-base); font-weight: 600; line-height: 1.4; letter-spacing: 0;
      color: var(--text-primary); }
    .spark { width: 18px; height: 18px; font-size: 18px; color: var(--primary); }
    .conversation { flex: 1; overflow-y: auto; padding: var(--space-4); display: flex; flex-direction: column; gap: var(--space-3); }
    .hint { margin: 0; color: var(--text-secondary); font-size: var(--font-size-sm); }
    .exchange { display: flex; flex-direction: column; gap: var(--space-2); }
    .bubble { padding: var(--space-2) var(--space-3); border-radius: var(--radius-md); white-space: pre-wrap; word-break: break-word;
      font-size: var(--font-size-base); max-width: 90%; }
    .mine { align-self: flex-end; background: var(--primary-strong); color: var(--on-primary); }
    .theirs { align-self: flex-start; color: var(--text-primary); background: var(--surface-2); }
    .error { align-self: flex-start; background: var(--danger-light); color: var(--danger-text); }
    .progress { display: flex; align-items: center; gap: var(--space-2); color: var(--text-secondary); font-size: var(--font-size-sm); }
    .citations { display: flex; flex-wrap: wrap; gap: var(--space-1); }
    .chip { display: inline-flex; align-items: center; gap: var(--space-1); max-width: 100%; padding: 4px var(--space-2);
      border: 1px solid var(--border); border-radius: var(--radius-sm); color: var(--primary); font-size: var(--font-size-sm);
      text-decoration: none; }
    .chip:hover { background: var(--surface-2); }
    .chip mat-icon { flex: none; font-size: 16px; width: 16px; height: 16px; }
    .proposal { border: 1px solid var(--primary); border-radius: var(--radius-md); padding: var(--space-3);
      background: var(--surface); display: flex; flex-direction: column; gap: var(--space-2); }
    .proposal.decided { border-color: var(--border); }
    .proposal-head { display: flex; align-items: center; gap: var(--space-2); font-size: var(--font-size-sm); color: var(--text-primary); }
    .proposal-head b { font-weight: 600; }
    .proposal-head mat-icon { flex: none; width: 16px; height: 16px; font-size: 16px; color: var(--text-muted); }
    .proposal-text { white-space: pre-wrap; word-break: break-word; color: var(--text-primary); background: var(--surface-2);
      border-radius: var(--radius-sm); padding: var(--space-2) var(--space-3); font-size: var(--font-size-base); }
    .links-warning { display: flex; align-items: center; gap: var(--space-1); color: var(--warning); font-size: var(--font-size-sm);
      word-break: break-all; }
    .links-warning mat-icon { flex: none; width: 16px; height: 16px; font-size: 16px; }
    .proposal-actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); justify-content: flex-end; }
    .expires { flex: 1 1 100%; color: var(--text-muted); font-size: var(--font-size-xs); }
    .proposal-status span { display: inline-flex; align-items: center; gap: var(--space-1); font-size: var(--font-size-sm);
      color: var(--text-secondary); }
    .proposal-status mat-icon { width: 16px; height: 16px; font-size: 16px; }
    .external h3 { display: flex; align-items: center; gap: var(--space-2); font-size: var(--font-size-sm); font-weight: 600;
      line-height: 1.4; letter-spacing: 0; color: var(--text-primary); margin: 0 0 var(--space-2); }
    .external h3 mat-icon { width: 16px; height: 16px; font-size: 16px; color: var(--text-muted); }
    .composer { display: flex; align-items: flex-end; gap: var(--space-2); padding: var(--space-3) var(--space-4);
      border-top: 1px solid var(--border); }
    .composer textarea { flex: 1; min-width: 0; resize: none; border: 1px solid var(--border-strong); border-radius: var(--radius-sm);
      padding: var(--space-2) var(--space-3); font: inherit; font-size: var(--font-size-base); background: var(--surface);
      color: var(--text-primary); }
    .composer textarea:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 1px var(--primary); }
    .composer textarea::placeholder { color: var(--text-muted); }
    .error-line { color: var(--danger-text); font-size: var(--font-size-sm); margin: 0 var(--space-4) var(--space-2); }
    @media (max-width: 600px) {
      .assistant-panel { border-left: 0; --mat-button-filled-container-height: 44px; --mat-button-outlined-container-height: 44px;
        --mat-icon-button-state-layer-size: 44px; }
      .chip, .proposal-status a { display: inline-flex; align-items: center; min-height: 44px; }
      .composer textarea { font-size: 16px; }
    }
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
