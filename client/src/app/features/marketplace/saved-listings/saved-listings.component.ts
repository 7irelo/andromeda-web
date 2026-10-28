import { Component, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../../core/services/api.service';
import { Listing } from '../../../models/listing.model';
import { ListingCardComponent } from '../listing-card/listing-card.component';

@Component({
    selector: 'app-saved-listings',
    imports: [CommonModule, RouterLink, MatButtonModule, MatIconModule, MatProgressSpinnerModule, ListingCardComponent],
    template: `
    <div class="page">
      <div class="page-header">
        <a mat-icon-button routerLink="/marketplace" aria-label="Back to Marketplace"><mat-icon>arrow_back</mat-icon></a>
        <h1>Saved listings</h1>
      </div>
      <p class="text-secondary text-sm">We'll let you know when a seller drops the price on something you saved.</p>

      <div class="loading-center" *ngIf="loading"><mat-spinner diameter="36"></mat-spinner></div>

      <div class="grid" *ngIf="!loading">
        <div class="cell" *ngFor="let l of listings">
          <app-listing-card [listing]="l"></app-listing-card>
          <button mat-button class="unsave" (click)="unsave(l)"><mat-icon>favorite</mat-icon> Remove</button>
        </div>
      </div>

      <div class="empty-state" *ngIf="!loading && !listings.length">
        <mat-icon>favorite_border</mat-icon>
        <p>Nothing saved yet. Tap Save on a listing to keep track of it.</p>
      </div>

      <div class="load-more" *ngIf="nextPage">
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

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this.load();
  }

  load(page = 1): void {
    if (page === 1) this.loading = true;
    this.api.getSavedListings(page).subscribe({
      next: (res) => {
        this.listings = page === 1 ? res.results : [...this.listings, ...res.results];
        this.nextPage = res.next ? page + 1 : null;
        this.loading = false;
      },
      error: () => (this.loading = false),
    });
  }

  unsave(l: Listing): void {
    this.api.likeListing(l.id).subscribe((res) => {
      if (!res.liked) this.listings = this.listings.filter((x) => x.id !== l.id);
    });
  }
}
