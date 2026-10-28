import { Component, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../core/services/api.service';
import { City, LISTING_CONDITIONS, Listing, ListingCategory } from '../../models/listing.model';
import { ListingCardComponent } from './listing-card/listing-card.component';
import { ListingFormComponent, apiError } from './listing-form/listing-form.component';
import { EmptyStateComponent, ErrorStateComponent, SkeletonComponent } from '../../shared/components/states';

type Sort = 'newest' | 'price_asc' | 'price_desc' | 'nearest' | '';

@Component({
    selector: 'app-marketplace',
    imports: [
        CommonModule, RouterLink, FormsModule,
        MatIconModule, MatButtonModule, MatInputModule, MatProgressSpinnerModule,
        MatFormFieldModule, MatSelectModule, MatSnackBarModule, ListingCardComponent, ListingFormComponent,
        EmptyStateComponent, ErrorStateComponent, SkeletonComponent,
    ],
    templateUrl: './marketplace.component.html',
    changeDetection: ChangeDetectionStrategy.Eager,
    styleUrls: ['./marketplace.component.scss']
})
export class MarketplaceComponent implements OnInit {
  listings: Listing[] = [];
  loading = false;
  loadError = '';
  loadingMore = false;
  nextPage: number | null = null;

  categories: ListingCategory[] = [];
  cities: City[] = [];
  readonly conditions = LISTING_CONDITIONS;
  readonly radii = [10, 25, 50, 100, 250];

  // Filters
  searchQuery = '';
  category = '';
  conditionFilter: string[] = [];
  minPrice: number | null = null;
  maxPrice: number | null = null;
  city = '';
  myPoint: { lat: number; lng: number } | null = null;
  radiusKm: number | null = null;
  sort: Sort = '';
  locating = false;
  showFilters = false;

  isCreating = false;

  constructor(
    private apiService: ApiService,
    private router: Router,
    private snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.apiService.getCategories().subscribe((c) => (this.categories = c));
    this.apiService.getMarketplaceCities().subscribe((c) => (this.cities = c));
    this.load();
  }

  get hasLocation(): boolean {
    return !!this.myPoint || !!this.city;
  }

  get activeFilterCount(): number {
    return [this.category, this.conditionFilter.length, this.minPrice !== null, this.maxPrice !== null,
      this.hasLocation].filter(Boolean).length;
  }

  private params(page = 1): Record<string, string> {
    const p: Record<string, string> = { page: String(page) };
    if (this.searchQuery.trim()) p['search'] = this.searchQuery.trim();
    if (this.category) p['category'] = this.category;
    if (this.conditionFilter.length) p['condition'] = this.conditionFilter.join(',');
    if (this.minPrice !== null && this.minPrice !== undefined) p['min_price'] = String(this.minPrice);
    if (this.maxPrice !== null && this.maxPrice !== undefined) p['max_price'] = String(this.maxPrice);
    if (this.myPoint) {
      p['lat'] = this.myPoint.lat.toFixed(3);
      p['lng'] = this.myPoint.lng.toFixed(3);
    } else if (this.city) {
      p['city'] = this.city;
    }
    if (this.hasLocation && this.radiusKm) p['radius_km'] = String(this.radiusKm);
    const sort = this.sort === 'nearest' && !this.hasLocation ? '' : this.sort;
    if (sort) p['sort'] = sort;
    return p;
  }

  load(): void {
    this.loading = true;
    this.loadError = '';
    this.apiService.getListings(this.params()).subscribe({
      next: (res) => {
        this.listings = res.results;
        this.nextPage = res.next ? 2 : null;
        this.loading = false;
      },
      error: (err: HttpErrorResponse) => {
        this.loading = false;
        this.loadError = apiError(err, 'Could not load listings');
      },
    });
  }

  loadMore(): void {
    if (!this.nextPage || this.loadingMore) return;
    this.loadingMore = true;
    const page = this.nextPage;
    this.apiService.getListings(this.params(page)).subscribe({
      next: (res) => {
        this.listings = [...this.listings, ...res.results];
        this.nextPage = res.next ? page + 1 : null;
        this.loadingMore = false;
      },
      error: () => (this.loadingMore = false),
    });
  }

  useMyLocation(): void {
    if (!('geolocation' in navigator)) {
      this.snackBar.open('Your browser cannot share a location.', 'Dismiss', { duration: 3000 });
      return;
    }
    this.locating = true;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        // Only used for this search, and coarsened before it leaves the browser.
        this.myPoint = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        this.city = '';
        this.locating = false;
        if (!this.radiusKm) this.radiusKm = 25;
        if (!this.sort) this.sort = 'nearest';
        this.load();
      },
      () => {
        this.locating = false;
        this.snackBar.open('Location permission was not given. Pick a city instead.', 'Dismiss', { duration: 3000 });
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 },
    );
  }

  pickCity(name: string): void {
    this.city = name;
    this.myPoint = null;
    if (name && !this.radiusKm) this.radiusKm = 50;
    this.load();
  }

  clearLocation(): void {
    this.city = '';
    this.myPoint = null;
    this.radiusKm = null;
    if (this.sort === 'nearest') this.sort = '';
    this.load();
  }

  clearFilters(): void {
    this.category = '';
    this.conditionFilter = [];
    this.minPrice = this.maxPrice = null;
    this.clearLocation();
  }

  openCreateDialog(): void {
    this.isCreating = true;
  }

  onCreated(listing: Listing): void {
    this.isCreating = false;
    this.router.navigate(['/marketplace', listing.id]);
  }
}
