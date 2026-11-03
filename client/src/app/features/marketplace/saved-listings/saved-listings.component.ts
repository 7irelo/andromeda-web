import { Component, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../../core/services/api.service';
import { Listing } from '../../../models/listing.model';
import { ListingCardComponent } from '../listing-card/listing-card.component';
import { EmptyStateComponent, ErrorStateComponent, SkeletonComponent } from '../../../shared/components/states';

@Component({
    selector: 'app-saved-listings',
    imports: [CommonModule, RouterLink, MatIconModule, ListingCardComponent,
        EmptyStateComponent, ErrorStateComponent, SkeletonComponent],
    template: `
    <div class="ui-page">
      <div class="ui-head">
        <a class="ui-icon-btn" routerLink="/marketplace" aria-label="Back to Marketplace"><mat-icon aria-hidden="true">arrow_back</mat-icon></a>
        <h1>Saved listings</h1>
      </div>
      <p class="intro">We'll let you know when a seller drops the price on something you saved.</p>

      <app-skeleton *ngIf="loading" variant="grid" [count]="3"></app-skeleton>
      <app-error-state *ngIf="!loading && failedPage === 1" (retry)="load(1)"></app-error-state>

      <div class="ui-grid" *ngIf="!loading && failedPage !== 1">
        <app-listing-card *ngFor="let l of listings" [listing]="l" (savedChange)="onSavedChange(l, $event)"></app-listing-card>
      </div>

      <app-empty-state *ngIf="!loading && !failedPage && !listings.length" icon="favorite_border" title="Nothing saved yet"
                       message="Tap Save on a listing to keep track of it.">
        <a class="ui-btn" routerLink="/marketplace">Browse Marketplace</a>
      </app-empty-state>

      <app-error-state *ngIf="failedPage > 1" [compact]="true" (retry)="load(failedPage)"></app-error-state>
      <div class="ui-more" *ngIf="nextPage && !failedPage">
        <button class="ui-btn" type="button" (click)="load(nextPage)">Load more</button>
      </div>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styleUrls: ['../ui.scss'],
    styles: [`
    .intro { margin: 0 0 var(--space-4); font-size: var(--font-size-sm); color: var(--text-secondary); }
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

  onSavedChange(l: Listing, saved: boolean): void {
    if (!saved) this.listings = this.listings.filter((x) => x.id !== l.id);
  }
}
