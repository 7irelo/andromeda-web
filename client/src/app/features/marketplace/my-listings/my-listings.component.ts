import { Component, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTabsModule } from '@angular/material/tabs';
import { ApiService } from '../../../core/services/api.service';
import { City, Listing, ListingCategory, ListingStatus, MyListingCounts } from '../../../models/listing.model';
import { primaryImage } from '../listing-card/listing-card.component';
import { ListingFormComponent, apiError } from '../listing-form/listing-form.component';

type Tab = ListingStatus | 'all';

@Component({
    selector: 'app-my-listings',
    imports: [
        CommonModule, RouterLink, MatButtonModule, MatIconModule, MatMenuModule, MatProgressSpinnerModule,
        MatSnackBarModule, MatTabsModule, ListingFormComponent,
    ],
    template: `
    <div class="page">
      <div class="page-header">
        <a mat-icon-button routerLink="/marketplace" aria-label="Back to Marketplace"><mat-icon>arrow_back</mat-icon></a>
        <h1>My listings</h1>
        <span class="spacer"></span>
        <button mat-flat-button color="primary" (click)="creating = true"><mat-icon>add</mat-icon> Create Listing</button>
      </div>

      <mat-tab-group [selectedIndex]="tabIndex" (selectedIndexChange)="selectTab($event)" mat-stretch-tabs="false">
        <mat-tab *ngFor="let t of tabs" [label]="t.label + ' (' + (counts?.[t.value] ?? 0) + ')'"></mat-tab>
      </mat-tab-group>

      <div class="loading-center" *ngIf="loading"><mat-spinner diameter="36"></mat-spinner></div>

      <div class="rows" *ngIf="!loading">
        <div class="row card" *ngFor="let l of listings">
          <a [routerLink]="'/marketplace/' + l.id" class="thumb"><img [src]="image(l)" [alt]="l.title" /></a>
          <div class="info">
            <a [routerLink]="'/marketplace/' + l.id" class="title font-semibold">{{ l.title }}</a>
            <div class="price">{{ l.currency }} {{ l.price }}</div>
            <div class="meta text-secondary text-xs">
              <span class="pill" [ngClass]="'pill-' + l.status">{{ l.status | titlecase }}</span>
              <span>{{ l.views_count }} views · {{ l.likes_count }} saves</span>
              <span *ngIf="l.rating.count">· ★ {{ l.rating.average | number:'1.1-1' }} ({{ l.rating.count }})</span>
            </div>
          </div>
          <div class="actions">
            <button mat-stroked-button (click)="editing = l"><mat-icon>edit</mat-icon> Edit</button>
            <button mat-icon-button [matMenuTriggerFor]="menu" aria-label="More actions"><mat-icon>more_vert</mat-icon></button>
            <mat-menu #menu="matMenu">
              <button mat-menu-item *ngIf="l.status === 'active'" (click)="setStatus(l, 'reserved')">
                <mat-icon>bookmark_added</mat-icon> Mark reserved
              </button>
              <button mat-menu-item *ngIf="l.status !== 'sold'" (click)="setStatus(l, 'sold')">
                <mat-icon>sell</mat-icon> Mark sold
              </button>
              <button mat-menu-item *ngIf="l.status !== 'active'" (click)="setStatus(l, 'active')">
                <mat-icon>replay</mat-icon> {{ l.status === 'draft' ? 'Publish' : 'Relist' }}
              </button>
              <button mat-menu-item (click)="remove(l)"><mat-icon color="warn">delete</mat-icon> Delete</button>
            </mat-menu>
          </div>
        </div>

        <div class="empty-state" *ngIf="!listings.length">
          <mat-icon>inventory_2</mat-icon>
          <p>Nothing {{ tab === 'all' ? 'here' : tab }} yet.</p>
        </div>

        <div class="load-more" *ngIf="nextPage">
          <button mat-stroked-button (click)="load(nextPage)">Load more</button>
        </div>
      </div>
    </div>

    <app-listing-form *ngIf="creating || editing" [listing]="editing" [categories]="categories" [cities]="cities"
                      (saved)="onSaved()" (closed)="creating = false; editing = null"></app-listing-form>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    .page { max-width: 900px; margin: 0 auto; padding: 24px 16px; }
    .page-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
    .page-header h1 { font-size: 24px; font-weight: 800; margin: 0; }
    .spacer { flex: 1; }
    .rows { display: flex; flex-direction: column; gap: 10px; margin-top: 16px; }
    .row { display: flex; align-items: center; gap: 14px; padding: 10px; }
    .thumb img { width: 76px; height: 76px; object-fit: cover; border-radius: 10px; display: block; }
    .info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
    .title { color: inherit; text-decoration: none; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .price { font-weight: 700; color: var(--primary); }
    .meta { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
    .pill { padding: 1px 8px; border-radius: 999px; background: var(--bg-secondary); font-weight: 600; }
    .pill-active { background: #dcfce7; color: #16a34a; }
    .pill-reserved { background: #fef3c7; color: #d97706; }
    .pill-sold { background: #e0e7ff; color: #4338ca; }
    .actions { display: flex; align-items: center; gap: 4px; }
    @media (max-width: 560px) { .row { flex-wrap: wrap; } .actions { width: 100%; justify-content: flex-end; } }
    .loading-center { display: flex; justify-content: center; padding: 48px; }
    .empty-state { display: flex; flex-direction: column; align-items: center; padding: 48px; color: var(--text-secondary); }
    .empty-state mat-icon { font-size: 48px; width: 48px; height: 48px; opacity: .3; }
    .load-more { display: flex; justify-content: center; padding: 16px; }
  `]
})
export class MyListingsComponent implements OnInit {
  readonly tabs: { value: Tab; label: string }[] = [
    { value: 'all', label: 'All' }, { value: 'active', label: 'Active' }, { value: 'reserved', label: 'Reserved' },
    { value: 'sold', label: 'Sold' }, { value: 'draft', label: 'Drafts' },
  ];
  tab: Tab = 'all';
  counts: MyListingCounts | null = null;
  listings: Listing[] = [];
  nextPage: number | null = null;
  loading = false;

  categories: ListingCategory[] = [];
  cities: City[] = [];
  creating = false;
  editing: Listing | null = null;

  constructor(private api: ApiService, private snackBar: MatSnackBar) {}

  get tabIndex(): number {
    return this.tabs.findIndex((t) => t.value === this.tab);
  }

  ngOnInit(): void {
    this.api.getCategories().subscribe((c) => (this.categories = c));
    this.api.getMarketplaceCities().subscribe((c) => (this.cities = c));
    this.refresh();
  }

  image(l: Listing): string {
    return primaryImage(l);
  }

  selectTab(index: number): void {
    this.tab = this.tabs[index].value;
    this.load();
  }

  refresh(): void {
    this.api.getMyListingCounts().subscribe((c) => (this.counts = c));
    this.load();
  }

  load(page = 1): void {
    if (page === 1) this.loading = true;
    this.api.getMyListings(this.tab === 'all' ? undefined : this.tab, page).subscribe({
      next: (res) => {
        this.listings = page === 1 ? res.results : [...this.listings, ...res.results];
        this.nextPage = res.next ? page + 1 : null;
        this.loading = false;
      },
      error: () => (this.loading = false),
    });
  }

  setStatus(l: Listing, status: ListingStatus): void {
    this.api.setListingStatus(l.id, status).subscribe({
      next: () => {
        this.snackBar.open(`Marked ${status === 'active' ? 'active' : status}`, 'Dismiss', { duration: 2500 });
        this.refresh();
      },
      error: (err: HttpErrorResponse) =>
        this.snackBar.open(apiError(err, 'Could not update the listing'), 'Dismiss', { duration: 3000 }),
    });
  }

  remove(l: Listing): void {
    if (!confirm(`Delete "${l.title}"? This can't be undone.`)) return;
    this.api.deleteListing(l.id).subscribe({
      next: () => this.refresh(),
      error: () => this.snackBar.open('Could not delete the listing', 'Dismiss', { duration: 3000 }),
    });
  }

  onSaved(): void {
    this.creating = false;
    this.editing = null;
    this.refresh();
  }
}
