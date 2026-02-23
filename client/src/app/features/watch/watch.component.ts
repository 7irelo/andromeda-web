import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../core/services/api.service';
import { Video } from '../../models/video.model';

@Component({
  selector: 'app-watch',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterLink,
    MatIconModule,
    MatButtonModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
  ],
  templateUrl: './watch.component.html',
  styleUrls: ['./watch.component.scss'],
})
export class WatchComponent implements OnInit {
  videos: Video[] = [];
  loading = false;
  uploading = false;
  uploadTitle = '';
  uploadDescription = '';
  selectedVideo: File | null = null;

  constructor(private apiService: ApiService, private snackBar: MatSnackBar) {}

  ngOnInit(): void {
    this.loadVideos();
  }

  loadVideos(): void {
    this.loading = true;
    this.apiService.getVideos().subscribe({
      next: (res) => {
        this.videos = res.results;
        this.loading = false;
      },
      error: () => (this.loading = false),
    });
  }

  onVideoSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.selectedVideo = input.files?.[0] ?? null;
    input.value = '';
  }

  uploadVideo(): void {
    if (!this.selectedVideo || this.uploading) return;

    const formData = new FormData();
    formData.append('video_file', this.selectedVideo);
    formData.append('title', this.uploadTitle.trim() || this.selectedVideo.name.replace(/\.[^/.]+$/, ''));
    formData.append('description', this.uploadDescription.trim());

    this.uploading = true;
    this.apiService.uploadVideo(formData).subscribe({
      next: (video) => {
        this.videos = [video, ...this.videos];
        this.selectedVideo = null;
        this.uploadTitle = '';
        this.uploadDescription = '';
        this.uploading = false;
        this.snackBar.open('Video uploaded', 'Dismiss', { duration: 3000 });
      },
      error: () => {
        this.uploading = false;
        this.snackBar.open('Failed to upload video', 'Dismiss', { duration: 3000 });
      },
    });
  }

  formatDuration(seconds: number): string {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  }
}
