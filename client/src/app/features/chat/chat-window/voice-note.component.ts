import { ChangeDetectionStrategy, ChangeDetectorRef, Component, Input, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { ApiService } from '../../../core/services/api.service';
import { Message } from '../../../models/chat.model';

/**
 * Voice-note player. The audio is a private attachment, so it's fetched with
 * the auth header and played from a blob: URL (allowed by `media-src blob:`).
 * The transcript sits under the player, collapsed by default.
 */
@Component({
  selector: 'app-voice-note',
  imports: [CommonModule, MatIconModule, MatButtonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="voice">
      <button mat-icon-button *ngIf="!src" (click)="load()" [disabled]="loading" aria-label="Play voice message">
        <mat-icon>{{ loading ? 'hourglass_empty' : 'play_arrow' }}</mat-icon>
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
    :host { display: block; min-width: 200px; }
    .voice { display: flex; align-items: center; gap: 4px; }
    audio { height: 36px; max-width: 260px; }
    .len { font-size: 13px; opacity: .8; }
    .toggle { background: none; border: none; padding: 2px 0; font-size: 12px; color: inherit;
              text-decoration: underline; cursor: pointer; opacity: .85; }
    .transcript { font-size: 13px; font-style: italic; opacity: .9; margin-top: 2px; white-space: pre-wrap; }
    .error { font-size: 12px; }
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
