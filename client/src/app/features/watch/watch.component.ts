import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../core/services/api.service';
import { Video } from '../../models/video.model';

@Component({
  selector: 'app-watch',
  standalone: true,
  imports: [CommonModule, RouterLink, MatIconModule, MatProgressSpinnerModule],
  templateUrl: './watch.component.html',
  styleUrls: ['./watch.component.scss'],
})
export class WatchComponent implements OnInit {
  videos: Video[] = [];
  loading = false;

  constructor(private apiService: ApiService) {}

  ngOnInit(): void {
    this.loading = true;
    this.apiService.getVideos().subscribe({
      next: (res) => {
        this.videos = res.results;
        this.loading = false;
      },
      error: () => (this.loading = false),
    });
  }

  formatDuration(seconds: number): string {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  }
}
