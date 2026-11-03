import { ChangeDetectionStrategy, ChangeDetectorRef, Component, Input, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../../core/services/api.service';
import { Message } from '../../../models/chat.model';

/**
 * Voice-note player. The audio is a private attachment, so it's fetched with
 * the auth header and played from a blob: URL (allowed by `media-src blob:`).
 * The transcript sits under the player, collapsed by default.
 */
@Component({
  selector: 'app-voice-note',
  imports: [CommonModule, MatIconModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="voice">
      <button type="button" class="play" *ngIf="!src" (click)="load()" [disabled]="loading" aria-label="Play voice message">
        <mat-icon aria-hidden="true">{{ loading ? 'hourglass_empty' : 'play_arrow' }}</mat-icon>
      </button>
      <audio *ngIf="src" [src]="src" controls autoplay preload="metadata"></audio>
      <span class="len" *ngIf="!src">{{ length }}</span>
    </div>
    <div class="error" *ngIf="error">{{ error }}</div>
    <div class="transcript" *ngIf="message.transcript_status === 'pending'">Transcribing...</div>
    <ng-container *ngIf="message.transcript_status === 'done' && message.transcript">
      <button class="toggle" type="button" (click)="showTranscript = !showTranscript"
              [attr.aria-expanded]="showTranscript">
        {{ showTranscript ? 'Hide transcript' : 'Show transcript' }}
      </button>
      <div class="transcript" *ngIf="showTranscript">{{ message.transcript }}</div>
    </ng-container>
  `,
  styles: [`
    :host { display: block; width: 240px; max-width: 100%; }
    .voice { display: flex; align-items: center; gap: 8px; }
    .play { display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; width: 36px; height: 36px;
            border: 1px solid currentColor; border-radius: var(--radius-sm); background: none; color: inherit; cursor: pointer; }
    .play:disabled { cursor: default; }
    .play mat-icon { width: 20px; height: 20px; font-size: 20px; }
    audio { width: 100%; height: 36px; }
    .len { font-size: 13px; }
    .toggle { display: block; margin-top: 4px; padding: 2px 0; border: none; background: none; font: inherit; font-size: 12px;
              color: inherit; text-decoration: underline; cursor: pointer; }
    .transcript { margin-top: 2px; font-size: 13px; font-style: italic; white-space: pre-wrap; }
    .error { margin-top: 4px; font-size: 12px; }
    @media (max-width: 768px) {
      :host { width: 200px; }
      .play { width: var(--touch-target); height: var(--touch-target); }
      .toggle { min-height: var(--touch-target); }
    }
  `],
})
export class VoiceNoteComponent implements OnDestroy {
  @Input({ required: true }) message!: Message;

  src: string | null = null;
  loading = false;
  error = '';
  showTranscript = false;

  constructor(private apiService: ApiService, private cdr: ChangeDetectorRef) {}

  get length(): string {
    const s = Math.round(this.message.duration_s ?? 0);
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  }

  load(): void {
    this.loading = true;
    this.error = '';
    this.apiService.getMessageFile(this.message.id).subscribe({
      next: (blob) => {
        this.src = URL.createObjectURL(blob);
        this.loading = false;
        this.cdr.markForCheck();
      },
      error: () => {
        this.loading = false;
        this.error = 'Could not load this voice message.';
        this.cdr.markForCheck();
      },
    });
  }

  ngOnDestroy(): void {
    if (this.src) URL.revokeObjectURL(this.src);
  }
}
