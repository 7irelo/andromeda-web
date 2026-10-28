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
        <img *ngIf="video.thumbnail_url; else noThumb" [src]="video.thumbnail_url" [alt]="video.title" class="thumbnail" loading="lazy" />
        <ng-template #noThumb>
          <div class="thumbnail placeholder">
            <mat-icon>{{ video.status === 'failed' ? 'error_outline' : video.status === 'processing' ? 'hourglass_top' : 'play_circle_outline' }}</mat-icon>
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
        <div class="video-title font-medium">
          <mat-icon class="lock" *ngIf="!video.is_public" title="Only you can see this">lock</mat-icon>{{ video.title }}
        </div>
        <div class="text-secondary text-xs" *ngIf="showUploader">{{ video.uploader.full_name || video.uploader.username }}</div>
        <div class="text-secondary text-xs">
          {{ video.views_count | number }} views · {{ video.created_at | date: 'mediumDate' }}
        </div>
        <div class="failure text-xs" *ngIf="video.status === 'failed' && video.failure_reason">{{ video.failure_reason }}</div>
      </div>
    </a>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: [`
    .video-card { text-decoration: none; color: inherit; display: flex; flex-direction: column; gap: 8px; }
    .video-card:hover { text-decoration: none; }
    .thumbnail-wrap { position: relative; border-radius: 12px; overflow: hidden; aspect-ratio: 16 / 9; background: #000; }
    .thumbnail { width: 100%; height: 100%; object-fit: cover; display: block; }
    .placeholder { display: flex; align-items: center; justify-content: center; color: #bbb; }
    .placeholder mat-icon { font-size: 40px; width: 40px; height: 40px; }
    .duration, .badge {
      position: absolute; bottom: 8px; right: 8px; background: rgba(0, 0, 0, 0.8); color: #fff;
      font-size: 12px; padding: 2px 6px; border-radius: 4px;
    }
    .badge { left: 8px; right: auto; top: 8px; bottom: auto; }
    .badge.failed { background: #c62828; }
    .resume { position: absolute; left: 0; right: 0; bottom: 0; height: 4px; background: rgba(255, 255, 255, 0.35); }
    .resume-fill { height: 100%; background: var(--primary); }
    .video-info { display: flex; flex-direction: column; gap: 2px; }
    .video-title { display: flex; align-items: center; gap: 4px; }
    .lock { font-size: 16px; width: 16px; height: 16px; color: var(--text-secondary); }
    .failure { color: #c62828; }
  `],
})
export class VideoCardComponent {
  @Input({ required: true }) video!: Video;
  @Input() showUploader = true;
  @Input() progressS = 0;

  format = formatDuration;
}
