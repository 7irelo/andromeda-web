import {
  ChangeDetectionStrategy, Component, EventEmitter, Input, OnChanges, OnDestroy, Output, SimpleChanges,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Subscription } from 'rxjs';
import { ApiService } from '../../../core/services/api.service';
import { AuthService } from '../../../core/services/auth.service';
import { ReplyFeedbackAction, ReplySuggestion } from '../../../models/assist.model';

/** Wait this long after a new incoming message before suggesting automatically. */
const AUTO_DEBOUNCE_MS = 1500;
/** At most one automatic request per room in this window: suggestions share the hourly AI allowance. */
const AUTO_MIN_INTERVAL_MS = 60_000;

const normalise = (s: string) => s.trim().replace(/\s+/g, ' ');

/**
 * Smart replies: a chip row above the chat composer. Tapping a chip fills the
 * input (it never sends). Typing cancels a request in flight. Hidden when the
 * member has turned AI off.
 */
@Component({
  selector: 'app-smart-replies',
  imports: [CommonModule, MatIconModule, MatTooltipModule],
  changeDetection: ChangeDetectionStrategy.Eager,
  template: `
    <div class="smart-replies" *ngIf="enabled" role="region" aria-label="Suggested replies">
      <ng-container *ngIf="suggestions.length; else idle">
        <button type="button" class="chip" *ngFor="let s of suggestions" (click)="choose(s)">{{ s.text }}</button>
        <button type="button" class="dismiss" (click)="dismiss()" aria-label="Dismiss suggestions"
                matTooltip="Dismiss">
          <mat-icon aria-hidden="true">close</mat-icon>
        </button>
      </ng-container>
      <ng-template #idle>
        <button type="button" class="chip ask" (click)="request()" [disabled]="loading" *ngIf="!unavailable">
          <mat-icon aria-hidden="true">auto_awesome</mat-icon>
          {{ loading ? 'Thinking…' : 'Suggest replies' }}
        </button>
        <span class="note" *ngIf="note" role="status">{{ note }}</span>
      </ng-template>
    </div>
  `,
  styles: [`
    .smart-replies { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 8px 16px 0; }
    .chip {
      flex-shrink: 0; height: 32px; max-width: 100%; padding: 0 10px; overflow: hidden;
      border: 1px solid var(--border-strong); border-radius: var(--radius-sm); background: var(--surface);
      font: inherit; font-size: 13px; color: var(--text-primary); text-overflow: ellipsis; white-space: nowrap; cursor: pointer;
      &:hover:not(:disabled) { background: var(--surface-2); }
      &:disabled { color: var(--text-muted); cursor: default; }
    }
    .chip.ask { display: inline-flex; align-items: center; gap: 6px; border-color: transparent; background: none;
                padding: 0 6px; font-size: 12px; color: var(--text-secondary); }
    .chip.ask mat-icon { width: 16px; height: 16px; font-size: 16px; color: var(--primary); }
    .note { font-size: 12px; color: var(--text-secondary); }
    .dismiss { display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; width: 28px; height: 28px;
               border: none; border-radius: var(--radius-sm); background: var(--surface); color: var(--text-secondary); cursor: pointer; }
    .dismiss:hover { background: var(--surface-2); color: var(--text-primary); }
    .dismiss mat-icon { width: 18px; height: 18px; font-size: 18px; }
    /* One scrolling row on phones: 44px chips would otherwise stack over the conversation. */
    @media (max-width: 768px) {
      .smart-replies { flex-wrap: nowrap; padding: 4px 12px 0; overflow-x: auto; scrollbar-width: none; }
      .chip { height: var(--touch-target); max-width: 75vw; }
      .dismiss { position: sticky; right: 0; width: var(--touch-target); height: var(--touch-target); }
    }
  `],
})
export class SmartRepliesComponent implements OnChanges, OnDestroy {
  @Input() roomId!: number;
  /** The composer's current text: typing cancels a request and hides stale chips. */
  @Input() draft = '';
  /** Bumped by the chat window for each new incoming message (not on initial load). */
  @Input() incomingTick = 0;
  /** Fills the composer with the chosen suggestion. */
  @Output() pick = new EventEmitter<string>();

  suggestions: ReplySuggestion[] = [];
  loading = false;
  unavailable = false;
  note = '';

  private inFlight?: Subscription;
  private autoTimer: ReturnType<typeof setTimeout> | null = null;
  private lastAutoAt = 0;
  private picked: ReplySuggestion | null = null;
  /** The draft we filled in ourselves, so it doesn't count as the user typing. */
  private filled: string | null = null;

  constructor(private api: ApiService, private auth: AuthService) {}

  get enabled(): boolean {
    const me = this.auth.currentUser;
    return !!me && !me.ai_opt_out;
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['roomId'] && !changes['roomId'].firstChange) this.reset();
    if (changes['draft'] && !changes['draft'].firstChange) this.onDraftChanged();
    if (changes['incomingTick'] && !changes['incomingTick'].firstChange) this.scheduleAuto();
  }

  ngOnDestroy(): void {
    this.cancel();
    if (this.autoTimer) clearTimeout(this.autoTimer);
  }

  request(): void {
    if (!this.enabled || this.loading || this.unavailable) return;
    this.cancel();
    this.loading = true;
    this.note = '';
    const roomId = this.roomId;
    this.inFlight = this.api.suggestReplies(roomId).subscribe({
      next: (res) => {
        this.loading = false;
        if (roomId !== this.roomId) return;
        this.suggestions = res.suggestions;
        if (!res.suggestions.length) this.note = 'No suggestions for this one.';
      },
      error: (err) => {
        this.loading = false;
        if (err?.status === 429) {
          this.note = "You've used your suggestions for now.";
          this.unavailable = true;
        } else if (err?.status === 403 || err?.status === 503) {
          this.unavailable = true;
        }
      },
    });
  }

  choose(s: ReplySuggestion): void {
    this.picked = s;
    this.filled = s.text;
    this.suggestions = [];
    this.pick.emit(s.text);
  }

  dismiss(): void {
    const ids = this.suggestions.map((s) => s.id);
    this.suggestions = [];
    if (ids.length) this.feedback('dismissed', ids);
  }

  /** Called by the chat window after a message is sent, to log accepted or edited. */
  noteSent(text: string): void {
    const picked = this.picked;
    this.picked = null;
    this.filled = null;
    this.suggestions = [];
    if (!picked) return;
    this.feedback(normalise(text) === normalise(picked.text) ? 'accepted' : 'edited', [picked.id]);
  }

  private onDraftChanged(): void {
    if (this.filled !== null && this.draft === this.filled) return;
    if (!this.draft.trim()) {
      // Cleared the input: a pick that was never sent is abandoned.
      this.picked = null;
      this.filled = null;
      return;
    }
    // The user is typing: never overwrite what they write.
    this.cancel();
    if (this.autoTimer) clearTimeout(this.autoTimer);
    this.suggestions = [];
  }

  private scheduleAuto(): void {
    if (this.autoTimer) clearTimeout(this.autoTimer);
    this.autoTimer = setTimeout(() => {
      this.autoTimer = null;
      const now = Date.now();
      if (this.draft.trim() || this.loading || now - this.lastAutoAt < AUTO_MIN_INTERVAL_MS) return;
      this.lastAutoAt = now;
      this.request();
    }, AUTO_DEBOUNCE_MS);
  }

  private cancel(): void {
    this.inFlight?.unsubscribe();
    this.inFlight = undefined;
    this.loading = false;
  }

  private reset(): void {
    this.cancel();
    if (this.autoTimer) clearTimeout(this.autoTimer);
    Object.assign(this, { suggestions: [], note: '', unavailable: false, picked: null, filled: null, lastAutoAt: 0 });
  }

  private feedback(action: ReplyFeedbackAction, ids: string[]): void {
    // Best effort: feedback never gets in the way of chatting.
    this.api.sendReplyFeedback(this.roomId, action, ids).subscribe({ error: () => undefined });
  }
}
