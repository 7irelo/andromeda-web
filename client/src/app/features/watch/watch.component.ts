import { Component, OnDestroy, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../core/services/api.service';
import { Video } from '../../models/video.model';
import { VideoCardComponent } from './video-card/video-card.component';
import { EmptyStateComponent, ErrorStateComponent, SkeletonComponent } from '../../shared/components/states';

const MAX_UPLOAD_BYTES = 500 * 1024 * 1024;
const POLL_MS = 10_000;

@Component({
    selector: 'app-watch',
    imports: [
        CommonModule,
        FormsModule,
        RouterLink,
        MatIconModule,
        MatButtonModule,
        MatButtonToggleModule,
        MatCheckboxModule,
        MatProgressSpinnerModule,
        MatSnackBarModule,
        VideoCardComponent, EmptyStateComponent, ErrorStateComponent, SkeletonComponent,
    ],
    templateUrl: './watch.component.html',
    changeDetection: ChangeDetectionStrategy.Eager,
    styleUrls: ['./watch.component.scss']
})
export class WatchComponent implements OnInit, OnDestroy {
  videos: Video[] = [];
  loading = false;
  loadError = false;
  uploading = false;
  uploadTitle = '';
  uploadDescription = '';
  uploadPublic = true;
  selectedVideo: File | null = null;
  feed: 'all' | 'subscriptions' = 'all';
  private pollTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(private apiService: ApiService, private snackBar: MatSnackBar) {}

  ngOnInit(): void {
    this.loadVideos();
  }

  ngOnDestroy(): void {
    this.stopPolling();
  }

  loadVideos(quiet = false): void {
    if (!quiet) {
      this.loading = true;
      this.loadError = false;
    }
    const params: Record<string, string> = this.feed === 'subscriptions' ? { feed: 'subscriptions' } : {};
    this.apiService.getVideos(params).subscribe({
      next: (res) => {
        this.videos = res.results;
        this.loading = false;
        this.schedulePoll();
      },
      error: () => {
        // A failed background refresh keeps what is on screen.
        if (!quiet) this.loadError = true;
        this.loading = false;
      },
    });
  }

  setFeed(feed: 'all' | 'subscriptions'): void {
    this.feed = feed;
    this.loadVideos();
  }

  /** Refresh while any of the signed-in user's uploads are still processing. */
  private schedulePoll(): void {
    this.stopPolling();
    if (this.videos.some((v) => v.status === 'processing')) {
      this.pollTimer = setTimeout(() => this.loadVideos(true), POLL_MS);
    }
  }

  private stopPolling(): void {
    if (this.pollTimer) clearTimeout(this.pollTimer);
    this.pollTimer = null;
  }

  onVideoSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    input.value = '';
    if (file && file.size > MAX_UPLOAD_BYTES) {
      this.snackBar.open('Videos must be smaller than 500 MB', 'Dismiss', { duration: 4000 });
      return;
    }
    this.selectedVideo = file;
  }

  uploadVideo(): void {
    if (!this.selectedVideo || this.uploading) return;

    const formData = new FormData();
    formData.append('video_file', this.selectedVideo);
    formData.append('title', (this.uploadTitle.trim() || this.selectedVideo.name.replace(/\.[^/.]+$/, '')).slice(0, 255));
    formData.append('description', this.uploadDescription.trim());
    formData.append('is_public', String(this.uploadPublic));

    this.uploading = true;
    this.apiService.uploadVideo(formData).subscribe({
      next: (video) => {
        this.videos = [video, ...this.videos];
        this.selectedVideo = null;
        this.uploadTitle = '';
        this.uploadDescription = '';
        this.uploading = false;
        this.schedulePoll();
        this.snackBar.open('Uploaded. We\'ll let you know when it\'s ready to watch.', 'Dismiss', { duration: 4000 });
      },
      error: (err: HttpErrorResponse) => {
        this.uploading = false;
        const detail = err.error?.video_file?.[0] || err.error?.detail || 'Failed to upload video';
        this.snackBar.open(detail, 'Dismiss', { duration: 4000 });
      },
    });
  }
}
