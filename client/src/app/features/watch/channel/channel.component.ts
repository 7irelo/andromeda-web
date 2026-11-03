import { Component, Input, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../../core/services/api.service';
import { AuthService } from '../../../core/services/auth.service';
import { Video, VideoChannel } from '../../../models/video.model';
import { VideoCardComponent } from '../video-card/video-card.component';

/** A user's videos tab: their videos, newest first, and a subscribe button. */
@Component({
  selector: 'app-video-channel',
  imports: [CommonModule, RouterLink, MatIconModule, MatProgressSpinnerModule, VideoCardComponent],
  template: `
    <div class="ui-page channel-page" *ngIf="channel; else waiting">
      <div class="channel-header card">
        <img [src]="channel.user.avatar_url || 'assets/default-avatar.png'" class="avatar lg" [alt]="channel.user.username" />
        <div class="channel-info">
          <h1>{{ channel.user.full_name || channel.user.username }}</h1>
          <div class="meta">
            &#64;{{ channel.user.username }} · {{ channel.subscribers_count | number }} subscribers ·
            {{ channel.videos_count | number }} videos
          </div>
          <a class="profile-link" [routerLink]="'/profile/' + channel.user.username">View profile</a>
        </div>
        <button *ngIf="!isSelf" class="ui-btn" [class.ui-btn-primary]="!channel.is_subscribed" type="button"
                (click)="toggleSubscribe()" [disabled]="busy">
          {{ channel.is_subscribed ? 'Subscribed' : 'Subscribe' }}
        </button>
      </div>

      <div class="ui-grid ui-grid-single">
        <app-video-card *ngFor="let v of videos" [video]="v" [showUploader]="false"></app-video-card>
      </div>
      <div class="ui-more" *ngIf="hasMore"><button class="ui-btn" type="button" (click)="loadMore()">Load more</button></div>
      <div class="empty-state" *ngIf="!loadingVideos && videos.length === 0">
        <mat-icon aria-hidden="true">videocam_off</mat-icon>
        <p>No videos yet</p>
      </div>
    </div>
    <ng-template #waiting>
      <div class="empty-state" *ngIf="notFound; else spinner">
        <mat-icon aria-hidden="true">person_off</mat-icon>
        <p>This channel isn't available.</p>
      </div>
      <ng-template #spinner><div class="loading-center"><mat-spinner diameter="40"></mat-spinner></div></ng-template>
    </ng-template>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrls: ['../../marketplace/ui.scss'],
    styles: [`
    .channel-header { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-4); padding: var(--space-4); margin-bottom: var(--space-4); }
    .channel-info { display: flex; flex: 1 1 200px; flex-direction: column; gap: 2px; min-width: 0; }
    .channel-info h1 { margin: 0; font-size: var(--font-size-xl); font-weight: 600; letter-spacing: -.01em; overflow-wrap: anywhere; }
    .meta { font-size: var(--font-size-sm); color: var(--text-secondary); }
    .profile-link { font-size: var(--font-size-sm); }
    .loading-center { display: flex; justify-content: center; padding: 60px; }
    .empty-state {
      display: flex; flex-direction: column; align-items: center; gap: var(--space-2); padding: var(--space-12) var(--space-4);
      font-size: var(--font-size-sm); color: var(--text-secondary);
    }
    .empty-state p { margin: 0; }
    .empty-state mat-icon { width: 36px; height: 36px; font-size: 36px; color: var(--text-muted); }
    @media (max-width: 600px) {
      .profile-link { display: inline-flex; align-items: center; min-height: var(--touch-target); align-self: flex-start; }
      .channel-header .ui-btn { flex: 1 1 100%; }
    }
  `],
})
export class ChannelComponent implements OnInit {
  @Input() userId!: string;
  channel: VideoChannel | null = null;
  videos: Video[] = [];
  notFound = false;
  busy = false;
  loadingVideos = false;
  hasMore = false;
  private page = 1;

  constructor(private apiService: ApiService, private auth: AuthService) {}

  get isSelf(): boolean {
    return !!this.channel && this.channel.user.id === this.auth.currentUser?.id;
  }

  ngOnInit(): void {
    const id = Number(this.userId);
    if (!Number.isInteger(id) || id <= 0) {
      this.notFound = true;
      return;
    }
    this.apiService.getVideoChannel(id).subscribe({
      next: (c) => {
        this.channel = c;
        this.loadVideos();
      },
      error: () => (this.notFound = true),
    });
  }

  private loadVideos(): void {
    if (!this.channel) return;
    this.loadingVideos = true;
    this.apiService.getVideos({ uploader: String(this.channel.user.id), page: String(this.page) }).subscribe({
      next: (res) => {
        this.videos = [...this.videos, ...res.results];
        this.hasMore = !!res.next;
        this.loadingVideos = false;
      },
      error: () => (this.loadingVideos = false),
    });
  }

  loadMore(): void {
    this.page += 1;
    this.loadVideos();
  }

  toggleSubscribe(): void {
    if (!this.channel || this.busy) return;
    const id = this.channel.user.id;
    const req = this.channel.is_subscribed
      ? this.apiService.unsubscribeFromChannel(id)
      : this.apiService.subscribeToChannel(id);
    this.busy = true;
    req.subscribe({
      next: (c) => {
        this.channel = c;
        this.busy = false;
      },
      error: () => (this.busy = false),
    });
  }
}
