import { Component, Input, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { Router, RouterLink } from '@angular/router';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { AuthService } from '../../../core/services/auth.service';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../../core/services/api.service';
import {
  City, LISTING_CONDITIONS, Listing, ListingCategory, ListingReview, ListingStatus,
} from '../../../models/listing.model';
import { ListingFormComponent, apiError } from '../listing-form/listing-form.component';

@Component({
    selector: 'app-listing-detail',
    imports: [
        CommonModule, FormsModule, RouterLink, MatIconModule,
        MatProgressSpinnerModule, MatSnackBarModule, ListingFormComponent,
    ],
    template: `
    <div class="ui-page listing-detail" *ngIf="listing">
      <div class="gallery">
        <div class="main-img-wrap"><img [src]="currentImage" alt="" class="main-img" /></div>
        <div class="thumb-row" *ngIf="listing.images.length > 1">
          <button type="button" class="thumb" *ngFor="let img of listing.images; let i = index"
                  (click)="currentImage = img.image" [class.active]="currentImage === img.image"
                  [attr.aria-pressed]="currentImage === img.image" [attr.aria-label]="photoLabel(i)">
            <img [src]="img.image" alt="" />
          </button>
        </div>
      </div>

      <aside class="summary">
        <div class="card panel">
          <h1>{{ listing.title }}</h1>
          <div class="price">{{ listing.price | currency:listing.currency:'symbol-narrow':'1.0-2' }}</div>
          <p class="tags">
            <span class="ui-tag">{{ conditionLabel }}</span>
            <span class="ui-tag tag-reserved" *ngIf="listing.status === 'reserved'">Reserved</span>
            <span *ngIf="listing.category">{{ listing.category.name }}</span>
            <span *ngIf="listing.location">· {{ listing.location }}</span>
          </p>

          <div class="stats">
            <span><mat-icon aria-hidden="true">visibility</mat-icon> {{ listing.views_count }} views</span>
            <span><mat-icon aria-hidden="true">favorite</mat-icon> {{ listing.likes_count }} saves</span>
            <span *ngIf="listing.rating.count">
              <mat-icon class="star" aria-hidden="true">star</mat-icon>
              {{ listing.rating.average | number:'1.1-1' }} ({{ listing.rating.count }} review{{ listing.rating.count === 1 ? '' : 's' }})
            </span>
          </div>

          <div class="action-buttons" *ngIf="isOwner">
            <span class="ui-tag">{{ listing.status | titlecase }}</span>
            <button class="ui-btn" type="button" (click)="editing = true"><mat-icon aria-hidden="true">edit</mat-icon> Edit</button>
            <button class="ui-btn" type="button" *ngIf="listing.status === 'active'" (click)="setStatus('reserved')">
              <mat-icon aria-hidden="true">bookmark_added</mat-icon> Mark reserved
            </button>
            <button class="ui-btn ui-btn-primary" type="button" *ngIf="listing.status !== 'sold'" (click)="setStatus('sold')">
              <mat-icon aria-hidden="true">sell</mat-icon> Mark as sold
            </button>
            <button class="ui-btn" type="button" *ngIf="listing.status !== 'active'" (click)="setStatus('active')">
              <mat-icon aria-hidden="true">replay</mat-icon> {{ listing.status === 'draft' ? 'Publish' : 'Relist' }}
            </button>
            <button class="ui-btn ui-btn-danger" type="button" (click)="remove()">
              <mat-icon aria-hidden="true">delete</mat-icon> Delete
            </button>
          </div>

          <div class="action-buttons" *ngIf="!isOwner">
            <button class="ui-btn ui-btn-primary message-btn" type="button" (click)="messageSeller()" [disabled]="messaging">
              <mat-icon aria-hidden="true">chat</mat-icon> Message Seller
            </button>
            <button class="ui-btn" type="button" (click)="toggleLike()" [class.is-on]="listing.is_liked">
              <mat-icon aria-hidden="true">{{ listing.is_liked ? 'favorite' : 'favorite_border' }}</mat-icon>
              {{ listing.is_liked ? 'Saved' : 'Save' }}
            </button>
          </div>
        </div>

        <div class="card panel seller-card" *ngIf="listing.seller">
          <a [routerLink]="'/profile/' + listing.seller.username" class="seller-link">
            <img [src]="listing.seller.avatar_url || 'assets/default-avatar.png'" class="avatar md" [alt]="listing.seller.username" />
            <div>
              <div class="seller-name">{{ listing.seller.full_name }}</div>
              <div class="muted">&#64;{{ listing.seller.username }}</div>
            </div>
          </a>
          <div class="seller-rating">
            <ng-container *ngIf="listing.seller_rating.count; else noRating">
              <span class="stars" [attr.aria-label]="listing.seller_rating.average + ' out of 5'">{{ stars(listing.seller_rating.average) }}</span>
              {{ listing.seller_rating.average | number:'1.1-1' }} · {{ listing.seller_rating.count }} seller review{{ listing.seller_rating.count === 1 ? '' : 's' }}
            </ng-container>
            <ng-template #noRating><span class="muted">No seller reviews yet</span></ng-template>
          </div>
        </div>
      </aside>

      <div class="details">
        <p class="description">{{ listing.description }}</p>

        <section class="reviews">
          <h2>Reviews</h2>
          <form class="review-form card" *ngIf="canReview" (ngSubmit)="submitReview()">
            <div class="star-picker" role="radiogroup" aria-label="Rating">
              <button type="button" *ngFor="let n of [1, 2, 3, 4, 5]" (click)="newRating = n"
                      [attr.aria-checked]="newRating === n" role="radio" [attr.aria-label]="n + ' stars'">
                <mat-icon aria-hidden="true" [class.on]="n <= newRating">{{ n <= newRating ? 'star' : 'star_border' }}</mat-icon>
              </button>
            </div>
            <label class="ui-field">
              How did it go? (optional)
              <textarea class="ui-control" rows="2" maxlength="2000" [(ngModel)]="newComment" name="comment"></textarea>
            </label>
            <div><button class="ui-btn ui-btn-primary" type="submit" [disabled]="!newRating || reviewing">Post review</button></div>
          </form>

          <div class="review" *ngFor="let r of reviews">
            <img [src]="r.reviewer.avatar_url || 'assets/default-avatar.png'" class="avatar sm" [alt]="r.reviewer.username" />
            <div>
              <div class="review-head"><span class="seller-name">{{ r.reviewer.full_name || r.reviewer.username }}</span>
                <span class="stars">{{ stars(r.rating) }}</span>
                <span class="muted">{{ r.created_at | date:'mediumDate' }}</span></div>
              <p *ngIf="r.comment">{{ r.comment }}</p>
            </div>
          </div>
          <p class="muted" *ngIf="!reviews.length">No reviews for this listing yet.</p>
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
    styleUrls: ['../ui.scss'],
    styles: [`
    .listing-detail {
      display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: var(--space-4) var(--space-6);
      grid-template-areas: 'gallery summary' 'details summary'; grid-template-rows: auto 1fr; align-items: start;
    }
    .gallery { grid-area: gallery; min-width: 0; }
    .summary { grid-area: summary; display: flex; flex-direction: column; gap: var(--space-3); min-width: 0; }
    .details { grid-area: details; display: flex; flex-direction: column; gap: var(--space-4); min-width: 0; }
    @media (max-width: 860px) {
      .listing-detail { grid-template-columns: minmax(0, 1fr); grid-template-areas: 'gallery' 'summary' 'details'; grid-template-rows: none; }
    }
    .main-img-wrap { overflow: hidden; aspect-ratio: 4 / 3; background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-lg); }
    .main-img { display: block; width: 100%; height: 100%; object-fit: cover; }
    .thumb-row { display: flex; flex-wrap: wrap; gap: var(--space-2); margin-top: var(--space-2); }
    .thumb {
      width: 64px; height: 64px; padding: 0; overflow: hidden; cursor: pointer; background: var(--surface-2);
      border: 1px solid var(--border); border-radius: var(--radius-sm);
    }
    .thumb img { display: block; width: 100%; height: 100%; object-fit: cover; }
    .thumb:hover { border-color: var(--border-strong); }
    .thumb.active { border-color: var(--primary); outline: 1px solid var(--primary); }
    .panel { display: flex; flex-direction: column; gap: var(--space-3); padding: var(--space-4); }
    h1 { margin: 0; font-size: var(--font-size-xl); font-weight: 600; letter-spacing: -.01em; overflow-wrap: anywhere; }
    .price { font-size: var(--font-size-xl); font-weight: 600; color: var(--text-primary); }
    .tags {
      display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-1) var(--space-2); margin: 0;
      font-size: var(--font-size-sm); color: var(--text-secondary);
    }
    .tag-reserved { color: var(--warning); background: var(--warning-light); }
    .description { margin: 0; font-size: var(--font-size-base); line-height: 1.6; color: var(--text-secondary); white-space: pre-line; overflow-wrap: anywhere; }
    .stats {
      display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-1) var(--space-3);
      font-size: var(--font-size-sm); color: var(--text-secondary);
    }
    .stats span { display: inline-flex; align-items: center; gap: var(--space-1); }
    .stats mat-icon { width: 16px; height: 16px; font-size: 16px; }
    .star, .stars { color: var(--warning); }
    .stars { margin: 0 var(--space-1); letter-spacing: 1px; }
    .seller-link { display: flex; align-items: center; gap: var(--space-3); color: inherit; text-decoration: none; }
    .seller-link:hover { color: inherit; text-decoration: none; }
    .seller-name { font-size: var(--font-size-sm); font-weight: 600; color: var(--text-primary); }
    .seller-rating { font-size: var(--font-size-sm); color: var(--text-secondary); }
    .muted { font-size: var(--font-size-sm); color: var(--text-muted); }
    .action-buttons { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); }
    .message-btn { flex: 1; }
    .reviews { display: flex; flex-direction: column; gap: var(--space-3); }
    .reviews h2 { margin: 0; font-size: var(--font-size-lg); font-weight: 600; }
    .review-form { display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-3); }
    .star-picker { display: flex; }
    .star-picker button {
      display: flex; align-items: center; justify-content: center; width: var(--touch-target); height: var(--touch-target);
      padding: 0; color: var(--text-muted); cursor: pointer; background: none; border: 0; border-radius: var(--radius-sm);
    }
    .star-picker mat-icon.on { color: var(--warning); }
    .review { display: flex; gap: var(--space-3); align-items: flex-start; font-size: var(--font-size-sm); }
    .review-head { display: flex; flex-wrap: wrap; align-items: center; gap: 0 var(--space-1); }
    .review p { margin: 2px 0 0; color: var(--text-secondary); overflow-wrap: anywhere; }
    .loading-center { display: flex; justify-content: center; padding: 60px; }
    @media (max-width: 600px) {
      .thumb { width: 56px; height: 56px; }
      .seller-link { min-height: var(--touch-target); }
    }
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

  photoLabel(index: number): string {
    return $localize`:@@marketplace.detail.showPhoto:Show photo ${index + 1}:number:`;
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
