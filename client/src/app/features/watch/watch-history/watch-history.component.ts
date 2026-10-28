import { Component, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../../core/services/api.service';
import { WatchHistoryEntry } from '../../../models/video.model';
import { VideoCardComponent } from '../video-card/video-card.component';
import { EmptyStateComponent, ErrorStateComponent, SkeletonComponent } from '../../../shared/components/states';

@Component({
  selector: 'app-watch-history',
  imports: [CommonModule, RouterLink, MatButtonModule, MatIconModule, MatProgressSpinnerModule, VideoCardComponent,
    EmptyStateComponent, ErrorStateComponent, SkeletonComponent],
  template: `
    <div class="history-page">
      <div class="header">
        <a mat-icon-button routerLink="/watch" aria-label="Back to Watch"><mat-icon>arrow_back</mat-icon></a>
        <h1>Watch history</h1>
        <button mat-stroked-button *ngIf="entries.length" (click)="clear()">
          <mat-icon>delete_sweep</mat-icon> Clear all
        </button>
      </div>

      <app-skeleton *ngIf="loading" variant="grid" [count]="6"></app-skeleton>
      <app-error-state *ngIf="!loading && loadError" [compact]="entries.length > 0" (retry)="retry()"></app-error-state>

      <div class="video-grid" *ngIf="!loading">
        <div class="entry" *ngFor="let e of entries">
          <app-video-card [video]="e.video" [progressS]="e.position_s"></app-video-card>
          <div class="entry-meta text-xs text-secondary">
            Watched {{ e.updated_at | date: 'medium' }}
            <button mat-icon-button (click)="remove(e)" aria-label="Remove from history">
              <mat-icon>close</mat-icon>
            </button>
          </div>
        </div>
      </div>

      <button mat-stroked-button class="more" *ngIf="hasMore && !loading && !loadError" (click)="loadMore()">Load more</button>

      <app-empty-state *ngIf="!loading && !loadError && entries.length === 0" icon="history"
                       title="No watch history" message="Videos you watch will show up here.">
        <a mat-stroked-button routerLink="/watch">Browse videos</a>
      </app-empty-state>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: [`
    .history-page { max-width: 1100px; margin: 0 auto; padding: 16px; }
    .header { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
    .header h1 { font-size: 24px; font-weight: 700; flex: 1; }
    .video-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; }
    .entry-meta { display: flex; align-items: center; justify-content: space-between; }
    .more { display: block; margin: 24px auto 0; }
    .loading-center { display: flex; justify-content: center; padding: 40px; }
    .empty-state { display: flex; flex-direction: column; align-items: center; padding: 60px; gap: 12px;
                   color: var(--text-secondary); }
    .empty-state mat-icon { font-size: 48px; width: 48px; height: 48px; opacity: 0.4; }
  `],
})
export class WatchHistoryComponent implements OnInit {
  entries: WatchHistoryEntry[] = [];
  loading = false;
  loadError = false;
  hasMore = false;
  private page = 1;

  constructor(private apiService: ApiService) {}

  ngOnInit(): void {
    this.load();
  }

  private load(): void {
    this.loading = this.page === 1;
    this.loadError = false;
    this.apiService.getWatchHistory(this.page).subscribe({
      next: (res) => {
        this.entries = [...this.entries, ...res.results];
        this.hasMore = !!res.next;
        this.loading = false;
      },
      error: () => {
        this.loading = false;
        this.loadError = true;
      },
    });
  }

  retry(): void {
    this.load();
  }

  loadMore(): void {
    this.page += 1;
    this.load();
  }

  remove(entry: WatchHistoryEntry): void {
    this.apiService.removeFromWatchHistory(entry.video.id).subscribe(() => {
      this.entries = this.entries.filter((e) => e !== entry);
    });
  }

  clear(): void {
    this.apiService.clearWatchHistory().subscribe(() => {
      this.entries = [];
      this.hasMore = false;
    });
  }
}
