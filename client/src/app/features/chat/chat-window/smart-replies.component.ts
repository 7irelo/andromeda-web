import {
  ChangeDetectionStrategy, Component, EventEmitter, Input, OnChanges, OnDestroy, Output, SimpleChanges,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
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
  imports: [CommonModule, MatIconModule, MatButtonModule, MatTooltipModule],
  changeDetection: ChangeDetectionStrategy.Eager,
  template: `
    <div class="smart-replies" *ngIf="enabled" role="region" aria-label="Suggested replies">
      <ng-container *ngIf="suggestions.length; else idle">
        <button type="button" class="chip" *ngFor="let s of suggestions" (click)="choose(s)">{{ s.text }}</button>
        <button mat-icon-button class="dismiss" (click)="dismiss()" aria-label="Dismiss suggestions"
                matTooltip="Dismiss">
          <mat-icon>close</mat-icon>
        </button>
      </ng-container>
      <ng-template #idle>
        <button type="button" class="chip ask" (click)="request()" [disabled]="loading" *ngIf="!unavailable">
          <mat-icon>auto_awesome</mat-icon>
          {{ loading ? 'Thinking…' : 'Suggest replies' }}
        </button>
        <span class="text-xs text-secondary" *ngIf="note" role="status">{{ note }}</span>
      </ng-template>
    </div>
  `,
  styles: [`
    .smart-replies { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 6px 12px 0; }
    .chip {
      border: 1px solid var(--primary); color: var(--primary); background: var(--surface); border-radius: 999px;
      padding: 4px 12px; font-size: 13px; cursor: pointer; max-width: 100%; overflow: hidden;
      text-overflow: ellipsis; white-space: nowrap; font-family: inherit;
      &:hover { background: var(--primary-light); }
      &:focus-visible { outline: 2px solid var(--primary); outline-offset: 1px; }
      &:disabled { opacity: .6; cursor: default; }
    }
    .chip.ask { display: inline-flex; align-items: center; gap: 4px; border-style: dashed; }
    .chip.ask mat-icon { font-size: 16px; width: 16px; height: 16px; }
    .dismiss { width: 28px; height: 28px; padding: 2px; }
    .dismiss mat-icon { font-size: 18px; width: 18px; height: 18px; }
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
