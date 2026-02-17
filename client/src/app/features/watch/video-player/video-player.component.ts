import { Component, Input, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { environment } from '../../../../environments/environment';

@Component({
  selector: 'app-video-player',
  standalone: true,
  imports: [CommonModule, MatButtonModule, MatIconModule],
  template: `
    <div class="player-page" *ngIf="video">
      <video controls class="video-player" [src]="asVideo(video).video_file"></video>
      <div class="video-meta">
        <h1>{{ asVideo(video).title }}</h1>
        <div class="meta-row">
          <span class="text-secondary">{{ asVideo(video).views_count | number }} views</span>
          <div class="actions">
            <button mat-button (click)="like()">
              <mat-icon>thumb_up</mat-icon> {{ asVideo(video).likes_count | number }}
            </button>
            <button mat-button><mat-icon>share</mat-icon> Share</button>
          </div>
        </div>
        <p class="text-secondary">{{ asVideo(video).description }}</p>
      </div>
    </div>
  `,
  styles: [`.player-page{max-width:900px;margin:0 auto;padding:16px} .video-player{width:100%;border-radius:8px;background:#000;max-height:500px} .video-meta{padding:12px 0;display:flex;flex-direction:column;gap:8px} .meta-row{display:flex;justify-content:space-between;align-items:center} .actions{display:flex;gap:4px}`]
})
export class VideoPlayerComponent implements OnInit {
  @Input() id!: string;
  video: unknown = null;

  constructor(private http: HttpClient) {}

  ngOnInit(): void {
    this.http.get(`${environment.apiUrl}/watch/videos/${this.id}/`).subscribe((v) => (this.video = v));
  }

  asVideo(v: unknown): { title: string; description: string; video_file: string; views_count: number; likes_count: number } {
    return v as ReturnType<typeof this.asVideo>;
  }

  like(): void {
    this.http.post(`${environment.apiUrl}/watch/videos/${this.id}/like/`, {}).subscribe();
  }
}
