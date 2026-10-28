import { Component, Input, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { Router, RouterLink } from '@angular/router';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { AuthService } from '../../../core/services/auth.service';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../../core/services/api.service';
import {
  City, LISTING_CONDITIONS, Listing, ListingCategory, ListingReview, ListingStatus,
} from '../../../models/listing.model';
import { ListingFormComponent, apiError } from '../listing-form/listing-form.component';

@Component({
    selector: 'app-listing-detail',
    imports: [
        CommonModule, FormsModule, RouterLink, MatButtonModule, MatFormFieldModule, MatIconModule, MatInputModule,
        MatProgressSpinnerModule, MatSnackBarModule, ListingFormComponent,
    ],
    template: `
    <div class="listing-detail" *ngIf="listing">
      <div class="listing-images">
        <img [src]="currentImage" alt="" class="main-img" />
        <div class="thumb-row">
          <img
            *ngFor="let img of listing.images"
            [src]="img.image"
            (click)="currentImage = img.image"
            class="thumb"
            [class.active]="currentImage === img.image"
          />
        </div>
      </div>

      <div class="listing-info">
        <div class="price">{{ listing.price | currency:listing.currency }}</div>
        <h1>{{ listing.title }}</h1>
        <p class="condition-location">
          <span class="badge" [ngClass]="'badge-' + listing.condition">{{ conditionLabel }}</span>
          <span class="badge badge-reserved" *ngIf="listing.status === 'reserved'">Reserved</span>
          <span class="text-secondary" *ngIf="listing.category">{{ listing.category.name }}</span>
          <span class="text-secondary" *ngIf="listing.location">· {{ listing.location }}</span>
        </p>
        <p class="description">{{ listing.description }}</p>

        <div class="listing-stats">
          <span class="text-secondary text-sm"><mat-icon class="stat-icon">visibility</mat-icon> {{ listing.views_count }} views</span>
          <span class="text-secondary text-sm"><mat-icon class="stat-icon">favorite</mat-icon> {{ listing.likes_count }} saves</span>
          <span class="text-secondary text-sm" *ngIf="listing.rating.count">
            <mat-icon class="stat-icon star">star</mat-icon>
            {{ listing.rating.average | number:'1.1-1' }} ({{ listing.rating.count }} review{{ listing.rating.count === 1 ? '' : 's' }})
          </span>
        </div>

        <div class="seller-card" *ngIf="listing.seller">
          <a [routerLink]="'/profile/' + listing.seller.username" class="seller-link">
            <img [src]="listing.seller.avatar_url || 'assets/default-avatar.png'" class="avatar md" [alt]="listing.seller.username" />
            <div>
              <div class="font-semibold">{{ listing.seller.full_name }}</div>
              <div class="text-secondary text-sm">&#64;{{ listing.seller.username }}</div>
            </div>
          </a>
          <div class="seller-rating text-sm">
            <ng-container *ngIf="listing.seller_rating.count; else noRating">
              <span class="stars" [attr.aria-label]="listing.seller_rating.average + ' out of 5'">{{ stars(listing.seller_rating.average) }}</span>
              {{ listing.seller_rating.average | number:'1.1-1' }} · {{ listing.seller_rating.count }} seller review{{ listing.seller_rating.count === 1 ? '' : 's' }}
            </ng-container>
            <ng-template #noRating><span class="text-secondary">No seller reviews yet</span></ng-template>
          </div>
        </div>

        <div class="action-buttons" *ngIf="isOwner">
          <span class="status-pill">{{ listing.status | titlecase }}</span>
          <button mat-stroked-button (click)="editing = true"><mat-icon>edit</mat-icon> Edit</button>
          <button mat-stroked-button *ngIf="listing.status === 'active'" (click)="setStatus('reserved')">
            <mat-icon>bookmark_added</mat-icon> Mark reserved
          </button>
          <button mat-flat-button color="primary" *ngIf="listing.status !== 'sold'" (click)="setStatus('sold')">
            <mat-icon>sell</mat-icon> Mark as sold
          </button>
          <button mat-stroked-button *ngIf="listing.status !== 'active'" (click)="setStatus('active')">
            <mat-icon>replay</mat-icon> {{ listing.status === 'draft' ? 'Publish' : 'Relist' }}
          </button>
          <button mat-stroked-button color="warn" (click)="remove()">
            <mat-icon>delete</mat-icon> Delete
          </button>
        </div>

        <div class="action-buttons" *ngIf="!isOwner">
          <button mat-flat-button color="primary" class="message-btn" (click)="messageSeller()" [disabled]="messaging">
            <mat-icon>chat</mat-icon> Message Seller
          </button>
          <button mat-stroked-button (click)="toggleLike()" [class.liked]="listing.is_liked">
            <mat-icon>{{ listing.is_liked ? 'favorite' : 'favorite_border' }}</mat-icon>
            {{ listing.is_liked ? 'Saved' : 'Save' }}
          </button>
        </div>

        <section class="reviews">
          <h2>Reviews</h2>
          <form class="review-form card" *ngIf="canReview" (ngSubmit)="submitReview()">
            <div class="star-picker" role="radiogroup" aria-label="Rating">
              <button type="button" *ngFor="let n of [1, 2, 3, 4, 5]" (click)="newRating = n"
                      [attr.aria-checked]="newRating === n" role="radio" [attr.aria-label]="n + ' stars'">
                <mat-icon [class.on]="n <= newRating">{{ n <= newRating ? 'star' : 'star_border' }}</mat-icon>
              </button>
            </div>
            <mat-form-field appearance="outline" class="w-full">
              <mat-label>How did it go? (optional)</mat-label>
              <textarea matInput rows="2" maxlength="2000" [(ngModel)]="newComment" name="comment"></textarea>
            </mat-form-field>
            <button mat-flat-button color="primary" type="submit" [disabled]="!newRating || reviewing">Post review</button>
          </form>

          <div class="review" *ngFor="let r of reviews">
            <img [src]="r.reviewer.avatar_url || 'assets/default-avatar.png'" class="avatar sm" [alt]="r.reviewer.username" />
            <div>
              <div class="text-sm"><span class="font-semibold">{{ r.reviewer.full_name || r.reviewer.username }}</span>
                <span class="stars">{{ stars(r.rating) }}</span>
                <span class="text-secondary text-xs">{{ r.created_at | date:'mediumDate' }}</span></div>
              <p class="text-sm" *ngIf="r.comment">{{ r.comment }}</p>
            </div>
          </div>
          <p class="text-secondary text-sm" *ngIf="!reviews.length">No reviews for this listing yet.</p>
        </section>
      </div>
    </div>

    <div class="loading-center" *ngIf="!listing">
      <mat-spinner diameter="40"></mat-spinner>
    </div>

    <app-listing-form *ngIf="editing && listing" [listing]="listing" [categories]="categories" [cities]="cities"
                      (saved)="onEdited($event)" (closed)="editing = false"></app-listing-form>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    .listing-detail {
      display: grid; grid-template-columns: 1fr 1fr; gap: 32px;
      max-width: 960px; margin: 0 auto; padding: 24px 16px;
    }
    @media (max-width: 768px) { .listing-detail { grid-template-columns: 1fr; } }
    .main-img { width: 100%; border-radius: 12px; object-fit: cover; max-height: 420px; }
    .thumb-row { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
    .thumb {
      width: 64px; height: 64px; object-fit: cover; border-radius: 8px;
      cursor: pointer; border: 2px solid transparent; transition: border-color .2s;
    }
    .thumb.active { border-color: var(--primary); }
    .thumb:hover { border-color: var(--primary); }
    .listing-info { display: flex; flex-direction: column; gap: 12px; }
    .price { font-size: 32px; font-weight: 800; color: var(--primary); }
    h1 { font-size: 22px; font-weight: 700; margin: 0; }
    .condition-location { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .badge { padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; }
    .badge-new { background: #dcfce7; color: #16a34a; }
    .badge-like_new { background: #e0f2fe; color: #0284c7; }
    .badge-good { background: var(--primary-light); color: var(--primary); }
    .badge-fair { background: #fef3c7; color: #d97706; }
    .badge-poor { background: #fee2e2; color: #dc2626; }
    .badge-reserved { background: #fde68a; color: #92400e; }
    .description { color: var(--text-secondary); line-height: 1.6; white-space: pre-line; }
    .listing-stats { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
    .stat-icon { font-size: 16px; width: 16px; height: 16px; vertical-align: middle; margin-right: 4px; }
    .star, .stars { color: #f59e0b; }
    .stars { letter-spacing: 1px; margin: 0 6px; }
    .seller-card {
      background: var(--surface-2); border: 1px solid var(--border); border-radius: 12px; padding: 12px 16px;
      display: flex; flex-direction: column; gap: 8px;
    }
    .seller-link { display: flex; align-items: center; gap: 12px; text-decoration: none; color: inherit; }
    .seller-link:hover { text-decoration: none; }
    .action-buttons { display: flex; gap: 10px; margin-top: 4px; flex-wrap: wrap; align-items: center; }
    .status-pill { padding: 4px 12px; border-radius: 999px; background: var(--bg-secondary); font-size: 13px; }
    .message-btn { flex: 1; }
    .liked { color: var(--danger); border-color: var(--danger); }
    .reviews { margin-top: 12px; display: flex; flex-direction: column; gap: 10px; }
    .reviews h2 { font-size: 18px; font-weight: 700; margin: 0; }
    .review-form { padding: 12px; display: flex; flex-direction: column; gap: 4px; }
    .star-picker { display: flex; }
    .star-picker button { background: none; border: 0; padding: 2px; cursor: pointer; color: var(--text-muted); }
    .star-picker mat-icon.on { color: #f59e0b; }
    .review { display: flex; gap: 10px; align-items: flex-start; }
    .review p { margin: 2px 0 0; }
    .w-full { width: 100%; }
    .loading-center { display: flex; justify-content: center; padding: 60px; }
  `]
})
export class ListingDetailComponent implements OnInit {
  @Input() id!: string;
  listing: Listing | null = null;
  currentImage = '';
  reviews: ListingReview[] = [];
  categories: ListingCategory[] = [];
  cities: City[] = [];

  messaging = false;
  editing = false;
  newRating = 0;
  newComment = '';
  reviewing = false;

  constructor(
    private apiService: ApiService,
    private authService: AuthService,
    private router: Router,
    private snackBar: MatSnackBar,
  ) {}

  get isOwner(): boolean {
    return !!this.listing && this.listing.seller?.id === this.authService.currentUser?.id;
  }

  get canReview(): boolean {
    const me = this.authService.currentUser?.id;
    return !!this.listing && !this.isOwner && !this.reviews.some((r) => r.reviewer.id === me);
  }

  get conditionLabel(): string {
    return LISTING_CONDITIONS.find((c) => c.value === this.listing?.condition)?.label ?? '';
  }

  stars(rating: number | null): string {
    const n = Math.round(rating ?? 0);
    return '★'.repeat(n) + '☆'.repeat(5 - n);
  }

  messageSeller(): void {
    if (!this.listing?.seller) return;
    this.messaging = true;
    this.apiService.createChatRoom({ member_ids: [this.listing.seller.id], room_type: 'direct' }).subscribe({
      next: (room) => this.router.navigate(['/chat', (room as { id: number }).id]),
      error: (err) => {
        this.messaging = false;
        this.snackBar.open(err?.error?.detail ?? 'This seller is not accepting messages', 'Dismiss', { duration: 3000 });
      },
    });
  }

  setStatus(status: ListingStatus): void {
    if (!this.listing) return;
    this.apiService.setListingStatus(this.listing.id, status).subscribe({
      next: (l) => (this.listing = { ...this.listing!, status: l.status }),
      error: () => this.snackBar.open('Could not update the listing', 'Dismiss', { duration: 3000 }),
    });
  }

  remove(): void {
    if (!this.listing || !confirm(`Delete "${this.listing.title}"? This can't be undone.`)) return;
    this.apiService.deleteListing(this.listing.id).subscribe({
      next: () => this.router.navigate(['/marketplace/mine']),
      error: () => this.snackBar.open('Could not delete the listing', 'Dismiss', { duration: 3000 }),
    });
  }

  ngOnInit(): void {
    const id = Number(this.id);
    this.apiService.getListing(id).subscribe({
      next: (l) => this.show(l),
      error: () => {
        this.snackBar.open('This listing is no longer available', 'Dismiss', { duration: 3000 });
        this.router.navigate(['/marketplace']);
      },
    });
    this.apiService.getListingReviews(id).subscribe((r) => (this.reviews = r));
    this.apiService.getCategories().subscribe((c) => (this.categories = c));
    this.apiService.getMarketplaceCities().subscribe((c) => (this.cities = c));
  }

  private show(l: Listing): void {
    this.listing = l;
    this.currentImage = l.images.find(i => i.is_primary)?.image || l.images[0]?.image || 'assets/default-listing.png';
  }

  onEdited(l: Listing): void {
    this.editing = false;
    this.show(l);
  }

  submitReview(): void {
    if (!this.listing || !this.newRating || this.reviewing) return;
    this.reviewing = true;
    const listingId = this.listing.id;
    this.apiService.reviewListing(listingId, { rating: this.newRating, comment: this.newComment.trim() }).subscribe({
      next: (review) => {
        this.reviews = [review, ...this.reviews];
        this.newRating = 0;
        this.newComment = '';
        this.reviewing = false;
        // Fold the new review into the aggregates (re-fetching the listing would count a view).
        if (this.listing) {
          const add = (r: { average: number | null; count: number }) => ({
            count: r.count + 1, average: ((r.average ?? 0) * r.count + review.rating) / (r.count + 1),
          });
          this.listing = { ...this.listing, rating: add(this.listing.rating), seller_rating: add(this.listing.seller_rating) };
        }
      },
      error: (err: HttpErrorResponse) => {
        this.reviewing = false;
        this.snackBar.open(apiError(err, 'Could not post the review'), 'Dismiss', { duration: 3000 });
      },
    });
  }

  toggleLike(): void {
    if (!this.listing) return;
    this.apiService.likeListing(this.listing.id).subscribe((res) => {
      if (this.listing) {
        this.listing.is_liked = res.liked;
        this.listing.likes_count += res.liked ? 1 : -1;
      }
    });
  }
}
