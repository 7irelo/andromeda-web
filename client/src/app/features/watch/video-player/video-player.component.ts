import { Component, ElementRef, Input, OnDestroy, OnInit, ViewChild, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import type Hls from 'hls.js';
import { ApiService } from '../../../core/services/api.service';
import { AuthService } from '../../../core/services/auth.service';
import { VideoChapter, VideoComment, VideoDetail } from '../../../models/video.model';
import { formatDuration } from '../video-card/video-card.component';

const SAVE_EVERY_MS = 10_000;
const POLL_MS = 10_000;

@Component({
    selector: 'app-video-player',
    imports: [CommonModule, RouterLink, FormsModule, MatButtonModule, MatIconModule, MatProgressSpinnerModule,
              MatSnackBarModule],
    template: `
    <div class="player-page" *ngIf="video">
      <div class="player-shell" *ngIf="video.status === 'ready'; else notReady">
        <video #player controls playsinline preload="metadata" class="video-player"
               [attr.poster]="video.thumbnail_url"></video>
        <div class="player-error" *ngIf="playbackError">{{ playbackError }}</div>
      </div>
      <ng-template #notReady>
        <div class="state-card" *ngIf="video.status === 'processing'">
          <mat-spinner diameter="32"></mat-spinner>
          <div>
            <div class="font-semibold">Processing your video</div>
            <div class="text-secondary text-sm">This page updates when it's ready to watch.</div>
          </div>
        </div>
        <div class="state-card failed" *ngIf="video.status === 'failed'">
          <mat-icon>error_outline</mat-icon>
          <div>
            <div class="font-semibold">We couldn't process this video</div>
            <div class="text-secondary text-sm">{{ video.failure_reason }}</div>
          </div>
          <button mat-stroked-button *ngIf="isOwner" (click)="retry()">Try again</button>
        </div>
      </ng-template>

      <div class="video-meta">
        <h1>
          <mat-icon class="lock" *ngIf="!video.is_public" title="Only you can see this">lock</mat-icon>{{ video.title }}
        </h1>
        <div class="meta-row">
          <span class="text-secondary">{{ video.views_count | number }} views · {{ video.created_at | date: 'mediumDate' }}</span>
          <div class="actions">
            <button mat-button (click)="like()" [class.liked]="video.is_liked" [disabled]="video.status !== 'ready'">
              <mat-icon>{{ video.is_liked ? 'thumb_up' : 'thumb_up_off_alt' }}</mat-icon>
              {{ video.likes_count | number }}
            </button>
            <button mat-button *ngIf="isOwner" (click)="toggleVisibility()">
              <mat-icon>{{ video.is_public ? 'public' : 'lock' }}</mat-icon>
              {{ video.is_public ? 'Public' : 'Private' }}
            </button>
          </div>
        </div>

        <div class="uploader-card">
          <a [routerLink]="'/watch/channel/' + video.uploader.id" class="uploader-link">
            <img [src]="video.uploader.avatar_url || 'assets/default-avatar.png'" class="avatar md" [alt]="video.uploader.username" />
            <div>
              <div class="font-semibold">{{ video.uploader.full_name || video.uploader.username }}</div>
              <div class="text-secondary text-sm">{{ video.channel.subscribers_count | number }} subscribers</div>
            </div>
          </a>
          <button *ngIf="!isOwner" mat-flat-button [color]="video.channel.is_subscribed ? undefined : 'primary'"
                  (click)="toggleSubscribe()" [disabled]="subscribing">
            {{ video.channel.is_subscribed ? 'Subscribed' : 'Subscribe' }}
          </button>
        </div>

        <p class="description" *ngIf="video.description">{{ video.description }}</p>

        <div class="chapters" *ngIf="video.chapters.length">
          <h3>Chapters</h3>
          <button type="button" class="chapter" *ngFor="let c of video.chapters; let i = index"
                  [class.active]="i === currentChapter" (click)="seek(c.start_s)">
            <span class="chapter-time">{{ format(c.start_s) }}</span>
            <span class="chapter-title">{{ c.title }}</span>
          </button>
        </div>

        <div class="transcript-block" *ngIf="video.has_transcript">
          <button mat-button (click)="toggleTranscript()">
            <mat-icon>subject</mat-icon> {{ transcript === null ? 'Show transcript' : 'Hide transcript' }}
          </button>
          <p class="transcript" *ngIf="transcript !== null">{{ transcript }}</p>
        </div>
        <div class="text-secondary text-xs" *ngIf="video.captions_status === 'pending'">Captions are being generated.</div>
      </div>

      <!-- Comments -->
      <div class="comments-section" *ngIf="video.status === 'ready'">
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

    <div class="loading-center" *ngIf="!video && !notFound">
      <mat-spinner diameter="40"></mat-spinner>
    </div>
    <div class="loading-center text-secondary" *ngIf="notFound">This video isn't available.</div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    .player-page { max-width: 900px; margin: 0 auto; padding: 16px; }
    .player-shell { position: relative; }
    .video-player { width: 100%; border-radius: 12px; background: #000; max-height: 506px; display: block; }
    .player-error {
      position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
      color: #fff; background: rgba(0, 0, 0, 0.7); border-radius: 12px; padding: 16px; text-align: center;
    }
    .state-card {
      display: flex; align-items: center; gap: 16px; padding: 24px; border-radius: 12px;
      background: var(--surface-2); border: 1px solid var(--border);
    }
    .state-card.failed mat-icon { color: #c62828; }
    .state-card button { margin-left: auto; }
    .video-meta { padding: 16px 0; display: flex; flex-direction: column; gap: 12px; }
    h1 { font-size: 20px; font-weight: 700; display: flex; align-items: center; gap: 6px; }
    .lock { color: var(--text-secondary); }
    .meta-row { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
    .actions { display: flex; gap: 4px; }
    .liked { color: var(--primary); }
    .uploader-card {
      display: flex; align-items: center; justify-content: space-between;
      background: var(--surface-2); border-radius: 12px; padding: 12px 16px;
      border: 1px solid var(--border);
    }
    .uploader-link { display: flex; align-items: center; gap: 12px; text-decoration: none; color: inherit; }
    .uploader-link:hover { text-decoration: none; }
    .description { color: var(--text-secondary); line-height: 1.6; white-space: pre-line; }
    .chapters { display: flex; flex-direction: column; gap: 4px; }
    .chapter {
      display: flex; gap: 12px; align-items: baseline; text-align: left; width: 100%;
      background: none; border: 1px solid transparent; border-radius: 8px; padding: 8px 10px;
      color: var(--text-primary); font: inherit; cursor: pointer;
    }
    .chapter:hover { background: var(--surface-2); }
    .chapter.active { border-color: var(--primary); background: var(--surface-2); }
    .chapter-time { color: var(--primary); font-variant-numeric: tabular-nums; min-width: 48px; }
    .transcript {
      max-height: 280px; overflow-y: auto; white-space: pre-line; line-height: 1.6;
      color: var(--text-secondary); background: var(--surface-2); border-radius: 8px; padding: 12px;
    }
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
export class VideoPlayerComponent implements OnInit, OnDestroy {
  @Input() id!: string;
  video: VideoDetail | null = null;
  comments: VideoComment[] = [];
  commentText = '';
  transcript: string | null = null;
  playbackError = '';
  notFound = false;
  subscribing = false;
  currentChapter = -1;
  format = formatDuration;

  private el: HTMLVideoElement | null = null;
  private hls: Hls | null = null;
  private captionsUrl: string | null = null;
  private lastSavedAt = 0;
  private lastSavedPos = 0;
  private resumed = false;
  private pollTimer: ReturnType<typeof setTimeout> | null = null;
  private destroyed = false;

  constructor(private apiService: ApiService, private auth: AuthService, private snackBar: MatSnackBar) {}

  /** The <video> only exists once the video is ready, so attach whenever it appears. */
  @ViewChild('player') set playerRef(ref: ElementRef<HTMLVideoElement> | undefined) {
    const el = ref?.nativeElement ?? null;
    if (el && el !== this.el) {
      this.el = el;
      void this.attach(el);
    }
  }

  get isOwner(): boolean {
    return !!this.video && this.video.uploader.id === this.auth.currentUser?.id;
  }

  ngOnInit(): void {
    this.load();
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    this.saveProgress(true);
    if (this.pollTimer) clearTimeout(this.pollTimer);
    this.hls?.destroy();
    if (this.captionsUrl) URL.revokeObjectURL(this.captionsUrl);
  }

  private load(): void {
    this.apiService.getVideo(Number(this.id)).subscribe({
      next: (v) => {
        this.video = v;
        if (v.status === 'ready') this.loadComments();
        if (v.status === 'processing' && !this.destroyed) {
          this.pollTimer = setTimeout(() => this.load(), POLL_MS);
        }
      },
      error: () => (this.notFound = true),
    });
  }

  private async attach(el: HTMLVideoElement): Promise<void> {
    const v = this.video;
    if (!v?.playback_url) return;
    el.addEventListener('loadedmetadata', () => this.resume(el));
    el.addEventListener('timeupdate', () => this.onTime(el));
    el.addEventListener('pause', () => this.saveProgress(true));
    el.addEventListener('ended', () => this.saveProgress(true));

    if (v.playback_type === 'file') {
      el.src = v.playback_url;
    } else {
      // Loaded on demand so hls.js isn't in the main bundle.
      const { default: HlsLib } = await import('hls.js');
      if (this.destroyed) return;
      if (HlsLib.isSupported()) {
        const hls = new HlsLib({ enableWorker: true, capLevelToPlayerSize: true });
        hls.on(HlsLib.Events.ERROR, (_event, data) => {
          if (!data.fatal) return;
          if (data.type === HlsLib.ErrorTypes.MEDIA_ERROR) {
            hls.recoverMediaError();
          } else {
            this.playbackError = 'This video could not be loaded. Try again later.';
            hls.destroy();
          }
        });
        hls.loadSource(v.playback_url);
        hls.attachMedia(el);
        this.hls = hls;
      } else if (el.canPlayType('application/vnd.apple.mpegurl')) {
        el.src = v.playback_url;  // Safari plays HLS natively
      } else {
        this.playbackError = "This browser can't play this video.";
        return;
      }
    }
    if (v.has_captions) this.addCaptions(el, v);
  }

  /** Captions come through the API (same visibility rules) and play from a blob: URL. */
  private addCaptions(el: HTMLVideoElement, v: VideoDetail): void {
    this.apiService.getVideoCaptions(v.id).subscribe({
      next: (vtt) => {
        if (this.destroyed) return;
        this.captionsUrl = URL.createObjectURL(new Blob([vtt], { type: 'text/vtt' }));
        const track = document.createElement('track');
        track.kind = 'captions';
        track.label = 'Captions';
        track.srclang = (v.transcript_language || 'en').split('-')[0];
        track.src = this.captionsUrl;
        el.appendChild(track);
      },
      error: () => undefined,  // playback works without captions
    });
  }

  private resume(el: HTMLVideoElement): void {
    if (this.resumed || !this.video) return;
    this.resumed = true;
    const at = this.video.resume_position_s;
    if (at > 5 && at < (el.duration || this.video.duration) - 10) {
      el.currentTime = at;
      this.lastSavedPos = at;
      this.snackBar.open(`Resumed at ${formatDuration(at)}`, 'Start over', { duration: 4000 })
        .onAction().subscribe(() => (el.currentTime = 0));
    }
  }

  private onTime(el: HTMLVideoElement): void {
    const t = el.currentTime;
    const chapters = this.video?.chapters ?? [];
    let idx = -1;
    chapters.forEach((c: VideoChapter, i: number) => { if (c.start_s <= t) idx = i; });
    this.currentChapter = idx;
    this.saveProgress(false);
  }

  /** Throttled: at most every 10 s while playing, plus on pause, end and leaving the page. */
  private saveProgress(force: boolean): void {
    const el = this.el;
    if (!el || !this.video || this.video.status !== 'ready' || !this.resumed) return;
    const pos = el.currentTime;
    const now = Date.now();
    if (Math.abs(pos - this.lastSavedPos) < 2) return;
    if (!force && now - this.lastSavedAt < SAVE_EVERY_MS) return;
    this.lastSavedAt = now;
    this.lastSavedPos = pos;
    this.apiService.saveVideoProgress(this.video.id, pos).subscribe({ error: () => undefined });
  }

  seek(seconds: number): void {
    if (!this.el) return;
    this.el.currentTime = seconds;
    void this.el.play().catch(() => undefined);
  }

  loadComments(): void {
    this.apiService.getVideoComments(Number(this.id)).subscribe((c) => (this.comments = c));
  }

  toggleTranscript(): void {
    if (this.transcript !== null) {
      this.transcript = null;
      return;
    }
    if (!this.video) return;
    this.apiService.getVideoTranscript(this.video.id).subscribe((t) => (this.transcript = t.transcript));
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

  toggleSubscribe(): void {
    if (!this.video || this.subscribing) return;
    const uploaderId = this.video.uploader.id;
    const req = this.video.channel.is_subscribed
      ? this.apiService.unsubscribeFromChannel(uploaderId)
      : this.apiService.subscribeToChannel(uploaderId);
    this.subscribing = true;
    req.subscribe({
      next: (ch) => {
        if (this.video) this.video.channel = { subscribers_count: ch.subscribers_count, is_subscribed: ch.is_subscribed };
        this.subscribing = false;
      },
      error: () => (this.subscribing = false),
    });
  }

  toggleVisibility(): void {
    if (!this.video) return;
    const isPublic = !this.video.is_public;
    this.apiService.updateVideo(this.video.id, { is_public: isPublic }).subscribe(() => {
      if (this.video) this.video.is_public = isPublic;
      this.snackBar.open(isPublic ? 'Anyone can watch this video now' : 'Only you can watch this video now',
        'Dismiss', { duration: 3000 });
    });
  }

  retry(): void {
    if (!this.video) return;
    this.apiService.retryVideo(this.video.id).subscribe(() => {
      if (this.video) this.video.status = 'processing';
      this.pollTimer = setTimeout(() => this.load(), POLL_MS);
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
