import { Component, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../../core/services/api.service';
import { WatchHistoryEntry } from '../../../models/video.model';
import { VideoCardComponent } from '../video-card/video-card.component';
import { EmptyStateComponent, ErrorStateComponent, SkeletonComponent } from '../../../shared/components/states';

@Component({
  selector: 'app-watch-history',
  imports: [CommonModule, RouterLink, MatIconModule, VideoCardComponent,
    EmptyStateComponent, ErrorStateComponent, SkeletonComponent],
  template: `
    <div class="ui-page">
      <div class="ui-head">
        <a class="ui-icon-btn" routerLink="/watch" aria-label="Back to Watch"><mat-icon aria-hidden="true">arrow_back</mat-icon></a>
        <h1>Watch history</h1>
        <button class="ui-btn" type="button" *ngIf="entries.length" (click)="clear()">
          <mat-icon aria-hidden="true">delete_sweep</mat-icon> Clear all
        </button>
      </div>

      <app-skeleton *ngIf="loading" variant="grid" [count]="6"></app-skeleton>
      <app-error-state *ngIf="!loading && loadError" [compact]="entries.length > 0" (retry)="retry()"></app-error-state>

      <div class="ui-grid ui-grid-single" *ngIf="!loading">
        <div class="entry" *ngFor="let e of entries">
          <app-video-card [video]="e.video" [progressS]="e.position_s"></app-video-card>
          <div class="entry-meta">
            Watched {{ e.updated_at | date: 'medium' }}
            <button class="ui-icon-btn" type="button" (click)="remove(e)" aria-label="Remove from history">
              <mat-icon aria-hidden="true">close</mat-icon>
            </button>
          </div>
        </div>
      </div>

      <div class="ui-more" *ngIf="hasMore && !loading && !loadError">
        <button class="ui-btn" type="button" (click)="loadMore()">Load more</button>
      </div>

      <app-empty-state *ngIf="!loading && !loadError && entries.length === 0" icon="history"
                       title="No watch history" message="Videos you watch will show up here.">
        <a class="ui-btn" routerLink="/watch">Browse videos</a>
      </app-empty-state>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrls: ['../../marketplace/ui.scss'],
    styles: [`
    .entry { min-width: 0; }
    .entry app-video-card { height: auto; }
    .entry-meta {
      display: flex; align-items: center; justify-content: space-between; gap: var(--space-2);
      padding: var(--space-1) 0 0 var(--space-1); font-size: var(--font-size-xs); color: var(--text-muted);
    }
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
