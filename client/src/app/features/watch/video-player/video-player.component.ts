import { Component, Input, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../../core/services/api.service';
import { Video, VideoComment } from '../../../models/video.model';

@Component({
  selector: 'app-video-player',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule, MatButtonModule, MatIconModule, MatProgressSpinnerModule],
  template: `
    <div class="player-page" *ngIf="video">
      <video controls class="video-player" [src]="video.video_file"></video>

      <div class="video-meta">
        <h1>{{ video.title }}</h1>
        <div class="meta-row">
          <span class="text-secondary">{{ video.views_count | number }} views</span>
          <div class="actions">
            <button mat-button (click)="like()" [class.liked]="video.is_liked">
              <mat-icon>{{ video.is_liked ? 'thumb_up' : 'thumb_up_off_alt' }}</mat-icon>
              {{ video.likes_count | number }}
            </button>
            <button mat-button><mat-icon>share</mat-icon> Share</button>
          </div>
        </div>

        <div class="uploader-card">
          <a [routerLink]="'/profile/' + video.uploader.username" class="uploader-link">
            <img [src]="video.uploader.avatar_url || 'assets/default-avatar.png'" class="avatar md" [alt]="video.uploader.username" />
            <div>
              <div class="font-semibold">{{ video.uploader.full_name }}</div>
              <div class="text-secondary text-sm">&#64;{{ video.uploader.username }}</div>
            </div>
          </a>
        </div>

        <p class="description" *ngIf="video.description">{{ video.description }}</p>
      </div>

      <!-- Comments -->
      <div class="comments-section">
        <h3>{{ comments.length }} {{ comments.length === 1 ? 'Comment' : 'Comments' }}</h3>

        <div class="comment-input">
          <input
            type="text"
            [(ngModel)]="commentText"
            placeholder="Add a comment..."
            (keyup.enter)="submitComment()"
            class="comment-field"
          />
          <button mat-icon-button (click)="submitComment()" [disabled]="!commentText.trim()">
            <mat-icon>send</mat-icon>
          </button>
        </div>

        <div class="comment" *ngFor="let c of comments">
          <img [src]="c.author.avatar_url || 'assets/default-avatar.png'" class="avatar sm" [alt]="c.author.username" />
          <div class="comment-bubble">
            <a [routerLink]="'/profile/' + c.author.username" class="author-name">{{ c.author.full_name }}</a>
            <p>{{ c.content }}</p>
            <span class="text-xs text-secondary">{{ timeAgo(c.created_at) }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="loading-center" *ngIf="!video">
      <mat-spinner diameter="40"></mat-spinner>
    </div>
  `,
  styles: [`
    .player-page { max-width: 900px; margin: 0 auto; padding: 16px; }
    .video-player { width: 100%; border-radius: 12px; background: #000; max-height: 500px; }
    .video-meta { padding: 16px 0; display: flex; flex-direction: column; gap: 12px; }
    h1 { font-size: 20px; font-weight: 700; }
    .meta-row { display: flex; justify-content: space-between; align-items: center; }
    .actions { display: flex; gap: 4px; }
    .liked { color: var(--primary); }
    .uploader-card {
      display: flex; align-items: center; justify-content: space-between;
      background: var(--surface-2); border-radius: 12px; padding: 12px 16px;
      border: 1px solid var(--border);
    }
    .uploader-link { display: flex; align-items: center; gap: 12px; text-decoration: none; color: inherit; }
    .uploader-link:hover { text-decoration: none; }
    .description { color: var(--text-secondary); line-height: 1.6; }
    .comments-section { margin-top: 24px; display: flex; flex-direction: column; gap: 16px; }
    h3 { font-size: 16px; font-weight: 700; }
    .comment-input { display: flex; align-items: center; gap: 8px; }
    .comment-field {
      flex: 1; background: var(--bg); border: 1px solid var(--border); border-radius: 20px;
      padding: 10px 16px; font-size: 14px; outline: none; color: var(--text-primary);
    }
    .comment-field:focus { border-color: var(--primary); }
    .comment-field::placeholder { color: var(--text-secondary); }
    .comment { display: flex; gap: 10px; }
    .comment-bubble {
      background: var(--bg); border-radius: 18px; padding: 10px 14px; flex: 1; font-size: 14px;
    }
    .author-name { font-weight: 600; font-size: 13px; color: var(--text-primary); text-decoration: none; display: block; }
    .author-name:hover { text-decoration: underline; }
    .comment-bubble p { margin-top: 2px; }
    .loading-center { display: flex; justify-content: center; padding: 60px; }
  `]
})
export class VideoPlayerComponent implements OnInit {
  @Input() id!: string;
  video: Video | null = null;
  comments: VideoComment[] = [];
  commentText = '';

  constructor(private apiService: ApiService) {}

  ngOnInit(): void {
    const videoId = Number(this.id);
    this.apiService.getVideo(videoId).subscribe((v) => {
      this.video = v;
      this.loadComments();
    });
  }

  loadComments(): void {
    this.apiService.getVideoComments(Number(this.id)).subscribe((c) => (this.comments = c));
  }

  like(): void {
    if (!this.video) return;
    this.apiService.likeVideo(this.video.id).subscribe((res) => {
      if (this.video) {
        this.video.is_liked = res.liked;
        this.video.likes_count += res.liked ? 1 : -1;
      }
    });
  }

  submitComment(): void {
    if (!this.commentText.trim()) return;
    this.apiService.createVideoComment(Number(this.id), { content: this.commentText }).subscribe((c) => {
      this.comments.unshift(c);
      this.commentText = '';
    });
  }

  timeAgo(dateStr: string): string {
    const diff = (Date.now() - new Date(dateStr).getTime()) / 1000;
    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  }
}
