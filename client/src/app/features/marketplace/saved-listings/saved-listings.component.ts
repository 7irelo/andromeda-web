import { Component, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../../core/services/api.service';
import { Listing } from '../../../models/listing.model';
import { ListingCardComponent } from '../listing-card/listing-card.component';
import { EmptyStateComponent, ErrorStateComponent, SkeletonComponent } from '../../../shared/components/states';

@Component({
    selector: 'app-saved-listings',
    imports: [CommonModule, RouterLink, MatButtonModule, MatIconModule, MatProgressSpinnerModule, ListingCardComponent,
        EmptyStateComponent, ErrorStateComponent, SkeletonComponent],
    template: `
    <div class="page">
      <div class="page-header">
        <a mat-icon-button routerLink="/marketplace" aria-label="Back to Marketplace"><mat-icon>arrow_back</mat-icon></a>
        <h1>Saved listings</h1>
      </div>
      <p class="text-secondary text-sm">We'll let you know when a seller drops the price on something you saved.</p>

      <app-skeleton *ngIf="loading" variant="grid" [count]="4" class="grid"></app-skeleton>
      <app-error-state *ngIf="!loading && failedPage === 1" (retry)="load(1)"></app-error-state>

      <div class="grid" *ngIf="!loading && failedPage !== 1">
        <div class="cell" *ngFor="let l of listings">
          <app-listing-card [listing]="l"></app-listing-card>
          <button mat-button class="unsave" (click)="unsave(l)" [attr.aria-label]="'Remove ' + l.title + ' from saved'"><mat-icon aria-hidden="true">favorite</mat-icon> Remove</button>
        </div>
      </div>

      <app-empty-state *ngIf="!loading && !failedPage && !listings.length" icon="favorite_border" title="Nothing saved yet"
                       message="Tap Save on a listing to keep track of it.">
        <a mat-stroked-button routerLink="/marketplace">Browse Marketplace</a>
      </app-empty-state>

      <app-error-state *ngIf="failedPage > 1" [compact]="true" (retry)="load(failedPage)"></app-error-state>
      <div class="load-more" *ngIf="nextPage && !failedPage">
        <button mat-stroked-button (click)="load(nextPage)">Load more</button>
      </div>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    .page { max-width: 1100px; margin: 0 auto; padding: 24px 16px; }
    .page-header { display: flex; align-items: center; gap: 8px; }
    .page-header h1 { font-size: 24px; font-weight: 800; margin: 0; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 18px; margin-top: 12px; }
    .cell { display: flex; flex-direction: column; gap: 4px; }
    .unsave { align-self: flex-start; color: var(--danger); }
    .loading-center { display: flex; justify-content: center; padding: 48px; }
    .empty-state { display: flex; flex-direction: column; align-items: center; padding: 64px 24px; color: var(--text-secondary); }
    .empty-state mat-icon { font-size: 48px; width: 48px; height: 48px; opacity: .3; }
    .load-more { display: flex; justify-content: center; padding: 16px; }
  `]
})
export class SavedListingsComponent implements OnInit {
  listings: Listing[] = [];
  nextPage: number | null = null;
  loading = false;
  /** Page number whose request failed, or 0. */
  failedPage = 0;

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this.load();
  }

  load(page = 1): void {
    if (page === 1) this.loading = true;
    this.failedPage = 0;
    this.api.getSavedListings(page).subscribe({
      next: (res) => {
        this.listings = page === 1 ? res.results : [...this.listings, ...res.results];
        this.nextPage = res.next ? page + 1 : null;
        this.loading = false;
      },
      error: () => {
        this.loading = false;
        this.failedPage = page;
      },
    });
  }

  unsave(l: Listing): void {
    this.api.likeListing(l.id).subscribe((res) => {
      if (!res.liked) this.listings = this.listings.filter((x) => x.id !== l.id);
    });
  }
}
