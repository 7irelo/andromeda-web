import { Component, Input, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../../core/services/api.service';
import { AuthService } from '../../../core/services/auth.service';
import { Video, VideoChannel } from '../../../models/video.model';
import { VideoCardComponent } from '../video-card/video-card.component';

/** A user's videos tab: their videos, newest first, and a subscribe button. */
@Component({
  selector: 'app-video-channel',
  imports: [CommonModule, RouterLink, MatButtonModule, MatIconModule, MatProgressSpinnerModule, VideoCardComponent],
  template: `
    <div class="channel-page" *ngIf="channel; else waiting">
      <div class="channel-header card">
        <img [src]="channel.user.avatar_url || 'assets/default-avatar.png'" class="avatar lg" [alt]="channel.user.username" />
        <div class="channel-info">
          <h1>{{ channel.user.full_name || channel.user.username }}</h1>
          <div class="text-secondary text-sm">
            &#64;{{ channel.user.username }} · {{ channel.subscribers_count | number }} subscribers ·
            {{ channel.videos_count | number }} videos
          </div>
          <a class="text-sm" [routerLink]="'/profile/' + channel.user.username">View profile</a>
        </div>
        <button *ngIf="!isSelf" mat-flat-button [color]="channel.is_subscribed ? undefined : 'primary'"
                (click)="toggleSubscribe()" [disabled]="busy">
          {{ channel.is_subscribed ? 'Subscribed' : 'Subscribe' }}
        </button>
      </div>

      <div class="video-grid">
        <app-video-card *ngFor="let v of videos" [video]="v" [showUploader]="false"></app-video-card>
      </div>
      <button mat-stroked-button class="more" *ngIf="hasMore" (click)="loadMore()">Load more</button>
      <div class="empty-state" *ngIf="!loadingVideos && videos.length === 0">
        <mat-icon>videocam_off</mat-icon>
        <p>No videos yet</p>
      </div>
    </div>
    <ng-template #waiting>
      <div class="empty-state" *ngIf="notFound; else spinner">
        <mat-icon>person_off</mat-icon>
        <p>This channel isn't available.</p>
      </div>
      <ng-template #spinner><div class="loading-center"><mat-spinner diameter="40"></mat-spinner></div></ng-template>
    </ng-template>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: [`
    .channel-page { max-width: 1100px; margin: 0 auto; padding: 16px; display: flex; flex-direction: column; gap: 20px; }
    .channel-header { display: flex; align-items: center; gap: 16px; padding: 16px; flex-wrap: wrap; }
    .channel-info { flex: 1; display: flex; flex-direction: column; gap: 4px; min-width: 200px; }
    .channel-info h1 { font-size: 22px; font-weight: 700; }
    .video-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; }
    .more { align-self: center; }
    .loading-center { display: flex; justify-content: center; padding: 60px; }
    .empty-state { display: flex; flex-direction: column; align-items: center; padding: 60px; gap: 12px;
                   color: var(--text-secondary); }
    .empty-state mat-icon { font-size: 48px; width: 48px; height: 48px; opacity: 0.4; }
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
