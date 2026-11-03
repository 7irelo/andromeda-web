import { Component, ElementRef, Input, OnDestroy, OnInit, ViewChild, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
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
    imports: [CommonModule, RouterLink, FormsModule, MatIconModule, MatProgressSpinnerModule,
              MatSnackBarModule],
    template: `
    <div class="ui-page player-page" *ngIf="video">
      <div class="player-shell" *ngIf="video.status === 'ready'; else notReady">
        <video #player controls playsinline preload="metadata" class="video-player"
               [attr.poster]="video.thumbnail_url"></video>
        <div class="player-error" *ngIf="playbackError">{{ playbackError }}</div>
      </div>
      <ng-template #notReady>
        <div class="state-card card" *ngIf="video.status === 'processing'">
          <mat-spinner diameter="32"></mat-spinner>
          <div>
            <div class="strong">Processing your video</div>
            <div class="muted">This page updates when it's ready to watch.</div>
          </div>
        </div>
        <div class="state-card card failed" *ngIf="video.status === 'failed'">
          <mat-icon aria-hidden="true">error_outline</mat-icon>
          <div>
            <div class="strong">We couldn't process this video</div>
            <div class="muted">{{ video.failure_reason }}</div>
          </div>
          <button class="ui-btn" type="button" *ngIf="isOwner" (click)="retry()">Try again</button>
        </div>
      </ng-template>

      <div class="video-meta">
        <h1>
          <mat-icon class="lock" *ngIf="!video.is_public" title="Only you can see this">lock</mat-icon><span>{{ video.title }}</span>
        </h1>
        <div class="meta-row">
          <span class="muted">{{ video.views_count | number }} views · {{ video.created_at | date: 'mediumDate' }}</span>
          <div class="actions">
            <button class="ui-btn" type="button" (click)="like()" [class.is-on]="video.is_liked" [disabled]="video.status !== 'ready'">
              <mat-icon aria-hidden="true">{{ video.is_liked ? 'thumb_up' : 'thumb_up_off_alt' }}</mat-icon>
              {{ video.likes_count | number }}
            </button>
            <button class="ui-btn" type="button" *ngIf="isOwner" (click)="toggleVisibility()">
              <mat-icon aria-hidden="true">{{ video.is_public ? 'public' : 'lock' }}</mat-icon>
              {{ video.is_public ? 'Public' : 'Private' }}
            </button>
          </div>
        </div>

        <div class="uploader-card card">
          <a [routerLink]="'/watch/channel/' + video.uploader.id" class="uploader-link">
            <img [src]="video.uploader.avatar_url || 'assets/default-avatar.png'" class="avatar md" [alt]="video.uploader.username" />
            <div>
              <div class="strong">{{ video.uploader.full_name || video.uploader.username }}</div>
              <div class="muted">{{ video.channel.subscribers_count | number }} subscribers</div>
            </div>
          </a>
          <button *ngIf="!isOwner" class="ui-btn" [class.ui-btn-primary]="!video.channel.is_subscribed" type="button"
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
          <button class="ui-btn" type="button" (click)="toggleTranscript()">
            <mat-icon aria-hidden="true">subject</mat-icon> {{ transcript === null ? 'Show transcript' : 'Hide transcript' }}
          </button>
          <p class="transcript" *ngIf="transcript !== null">{{ transcript }}</p>
        </div>
        <div class="muted small" *ngIf="video.captions_status === 'pending'">Captions are being generated.</div>
      </div>

      <!-- Comments -->
      <div class="comments-section" *ngIf="video.status === 'ready'">
        <h3>{{ comments.length }} {{ comments.length === 1 ? 'Comment' : 'Comments' }}</h3>

        <div class="comment-input">
          <input class="ui-control" type="text" [(ngModel)]="commentText" placeholder="Add a comment..."
                 aria-label="Add a comment" i18n-aria-label="@@watch.addComment" (keyup.enter)="submitComment()" />
          <button class="ui-btn ui-btn-primary send" type="button" (click)="submitComment()" [disabled]="!commentText.trim()"
                  aria-label="Post comment" i18n-aria-label="@@watch.postComment">
            <mat-icon aria-hidden="true">send</mat-icon>
          </button>
        </div>

        <div class="comment" *ngFor="let c of comments">
          <img [src]="c.author.avatar_url || 'assets/default-avatar.png'" class="avatar sm" [alt]="c.author.username" />
          <div class="comment-body">
            <a [routerLink]="'/profile/' + c.author.username" class="author-name">{{ c.author.full_name }}</a>
            <span class="muted small">{{ timeAgo(c.created_at) }}</span>
            <p>{{ c.content }}</p>
          </div>
        </div>
      </div>
    </div>

    <div class="loading-center" *ngIf="!video && !notFound">
      <mat-spinner diameter="40"></mat-spinner>
    </div>
    <div class="loading-center muted" *ngIf="notFound">This video isn't available.</div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styleUrls: ['../../marketplace/ui.scss'],
    styles: [`
    .player-page { max-width: 960px; }
    .player-shell { position: relative; overflow: hidden; background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-lg); }
    .video-player { display: block; width: 100%; aspect-ratio: 16 / 9; max-height: 70vh; }
    .player-error {
      position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; padding: var(--space-4);
      color: var(--text-primary); text-align: center; background: var(--surface);
    }
    .state-card { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-4); padding: var(--space-6); }
    .state-card > div { flex: 1 1 200px; min-width: 0; }
    .state-card.failed mat-icon { color: var(--danger-text); }
    .strong { font-size: var(--font-size-sm); font-weight: 600; color: var(--text-primary); }
    .muted { font-size: var(--font-size-sm); color: var(--text-secondary); }
    .small { font-size: var(--font-size-xs); color: var(--text-muted); }
    .video-meta { display: flex; flex-direction: column; gap: var(--space-3); padding: var(--space-4) 0; }
    h1 {
      display: flex; align-items: flex-start; gap: var(--space-1); margin: 0;
      font-size: var(--font-size-xl); font-weight: 600; letter-spacing: -.01em; overflow-wrap: anywhere;
    }
    h1 span { min-width: 0; }
    .lock { flex: none; color: var(--text-muted); }
    .meta-row { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--space-2); }
    .actions { display: flex; gap: var(--space-2); }
    .uploader-card { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--space-3); padding: var(--space-3) var(--space-4); }
    .uploader-link { display: flex; align-items: center; gap: var(--space-3); min-width: 0; color: inherit; text-decoration: none; }
    .uploader-link:hover { color: inherit; text-decoration: none; }
    .description { margin: 0; line-height: 1.6; color: var(--text-secondary); white-space: pre-line; overflow-wrap: anywhere; }
    .chapters { display: flex; flex-direction: column; gap: 2px; }
    .chapters h3 { margin-bottom: var(--space-1); }
    .chapter {
      display: flex; align-items: baseline; gap: var(--space-3); width: 100%; min-height: var(--touch-target); padding: var(--space-2) 10px;
      font: inherit; font-size: var(--font-size-sm); color: var(--text-primary); text-align: left; cursor: pointer;
      background: none; border: 1px solid transparent; border-radius: var(--radius-sm);
    }
    .chapter:hover { background: var(--surface-2); }
    .chapter.active { background: var(--primary-light); border-color: var(--primary); }
    .chapter-time { min-width: 48px; color: var(--primary); font-variant-numeric: tabular-nums; }
    .transcript {
      max-height: 280px; padding: var(--space-3); margin: var(--space-2) 0 0; overflow-y: auto; line-height: 1.6;
      color: var(--text-secondary); white-space: pre-line; background: var(--surface-2); border-radius: var(--radius-sm);
    }
    .comments-section { display: flex; flex-direction: column; gap: var(--space-3); padding-top: var(--space-4); border-top: 1px solid var(--border); }
    h3 { margin: 0; font-size: var(--font-size-base); font-weight: 600; }
    .comment-input { display: flex; align-items: center; gap: var(--space-2); }
    .send { flex: none; width: 36px; padding: 0; }
    .comment { display: flex; gap: var(--space-3); font-size: var(--font-size-sm); }
    .comment-body { flex: 1; min-width: 0; }
    .author-name { margin-right: var(--space-1); font-weight: 600; color: var(--text-primary); text-decoration: none; }
    .author-name:hover { color: var(--text-primary); text-decoration: underline; }
    .comment-body p { margin: 2px 0 0; color: var(--text-secondary); overflow-wrap: anywhere; }
    .loading-center { display: flex; justify-content: center; padding: 60px; }
    @media (max-width: 600px) {
      .send { width: var(--touch-target); }
      .uploader-link { min-height: var(--touch-target); }
      .author-name { display: inline-flex; align-items: center; min-height: var(--touch-target); }
      .uploader-card .ui-btn { flex: 1 1 100%; }
    }
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
