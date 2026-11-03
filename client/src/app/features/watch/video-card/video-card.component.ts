import { Component, Input, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { Video } from '../../../models/video.model';

export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds || 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = (total % 60).toString().padStart(2, '0');
  return h ? `${h}:${m.toString().padStart(2, '0')}:${s}` : `${m}:${s}`;
}

/** Grid card for a video, with an optional resume bar (watch history). */
@Component({
  selector: 'app-video-card',
  imports: [CommonModule, RouterLink, MatIconModule],
  template: `
    <a class="video-card" [routerLink]="'/watch/' + video.id">
      <div class="thumbnail-wrap">
        <img *ngIf="video.thumbnail_url; else noThumb" [src]="video.thumbnail_url" alt="" class="thumbnail" loading="lazy" />
        <ng-template #noThumb>
          <div class="thumbnail placeholder">
            <mat-icon aria-hidden="true">{{ video.status === 'failed' ? 'error_outline' : video.status === 'processing' ? 'hourglass_top' : 'play_circle_outline' }}</mat-icon>
          </div>
        </ng-template>
        <span class="badge" *ngIf="video.status === 'processing'">Processing</span>
        <span class="badge failed" *ngIf="video.status === 'failed'">Failed</span>
        <span class="duration" *ngIf="video.status === 'ready' && video.duration">{{ format(video.duration) }}</span>
        <div class="resume" *ngIf="progressS && video.duration">
          <div class="resume-fill" [style.width.%]="(progressS / video.duration) * 100"></div>
        </div>
      </div>
      <div class="video-info">
        <div class="video-title">
          <mat-icon class="lock" *ngIf="!video.is_public" title="Only you can see this">lock</mat-icon><span>{{ video.title }}</span>
        </div>
        <div class="meta" *ngIf="showUploader">{{ video.uploader.full_name || video.uploader.username }}</div>
        <div class="meta">
          {{ video.views_count | number }} views · {{ video.created_at | date: 'mediumDate' }}
        </div>
        <div class="failure" *ngIf="video.status === 'failed' && video.failure_reason">{{ video.failure_reason }}</div>
      </div>
    </a>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: [`
    :host { display: block; min-width: 0; }
    .video-card {
      display: block; box-sizing: border-box; height: 100%; overflow: hidden; color: inherit; text-decoration: none;
      background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
      transition: border-color var(--motion-fast);
    }
    .video-card:hover { color: inherit; text-decoration: none; border-color: var(--border-strong); }
    .thumbnail-wrap { position: relative; aspect-ratio: 16 / 9; overflow: hidden; background: var(--surface-2); border-bottom: 1px solid var(--border); }
    .thumbnail { display: block; width: 100%; height: 100%; object-fit: cover; }
    .placeholder { display: flex; align-items: center; justify-content: center; color: var(--text-muted); }
    .placeholder mat-icon { width: 36px; height: 36px; font-size: 36px; }
    .duration, .badge {
      position: absolute; right: var(--space-2); bottom: var(--space-2); padding: 1px 6px;
      font-size: var(--font-size-xs); font-weight: 500; font-variant-numeric: tabular-nums; color: var(--text-primary);
      background: var(--surface); border: 1px solid var(--border); border-radius: 6px;
    }
    .badge { top: var(--space-2); right: auto; bottom: auto; left: var(--space-2); }
    .badge.failed { color: var(--danger-text); }
    .resume { position: absolute; right: 0; bottom: 0; left: 0; height: 4px; background: var(--border); }
    .resume-fill { height: 100%; background: var(--primary-strong); }
    .video-info { display: flex; flex-direction: column; gap: 2px; padding: var(--space-3); }
    .video-title {
      display: flex; align-items: flex-start; gap: var(--space-1); margin-bottom: 2px;
      font-size: var(--font-size-base); font-weight: 600; line-height: 1.35; color: var(--text-primary);
    }
    .video-title span {
      display: -webkit-box; overflow: hidden; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2; overflow-wrap: anywhere;
    }
    .lock { flex: none; width: 16px; height: 16px; font-size: 16px; color: var(--text-muted); }
    .meta { font-size: var(--font-size-xs); color: var(--text-muted); }
    .failure { font-size: var(--font-size-xs); color: var(--danger-text); }
  `],
})
export class VideoCardComponent {
  @Input({ required: true }) video!: Video;
  @Input() showUploader = true;
  @Input() progressS = 0;

  format = formatDuration;
}
