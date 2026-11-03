import { Component, EventEmitter, Input, Output, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../../core/services/api.service';
import { AuthService } from '../../../core/services/auth.service';
import { Listing, LISTING_CONDITIONS } from '../../../models/listing.model';

export function primaryImage(listing: Listing): string {
  const primary = listing.images?.find((i) => i.is_primary);
  return primary?.image || listing.images?.[0]?.image || 'assets/default-listing.png';
}

@Component({
    selector: 'app-listing-card',
    imports: [CommonModule, RouterLink, MatIconModule, MatSnackBarModule],
    template: `
    <article class="listing-card">
      <a class="card-link" [routerLink]="'/marketplace/' + listing.id">
        <div class="media">
          <img [src]="image" alt="" loading="lazy" />
          <span class="status" *ngIf="listing.status !== 'active'">{{ listing.status | titlecase }}</span>
        </div>
        <div class="info">
          <div class="title">{{ listing.title }}</div>
          <div class="price-row">
            <span class="price">{{ listing.price | currency:listing.currency:'symbol-narrow':'1.0-2' }}</span>
            <span class="meta">{{ conditionLabel }}</span>
          </div>
          <div class="meta line">
            {{ listing.location || 'Location not specified' }}<ng-container *ngIf="listing.distance_km !== null && listing.distance_km !== undefined"> · ~{{ listing.distance_km }} km</ng-container>
          </div>
          <div class="meta line" *ngIf="listing.seller_rating?.count">
            {{ listing.seller_rating.average | number:'1.1-1' }} seller ({{ listing.seller_rating.count }})
          </div>
        </div>
      </a>
      <button class="save" type="button" *ngIf="!isMine" (click)="toggleSave()" [disabled]="saving"
              [class.saved]="listing.is_liked" [attr.aria-label]="saveLabel">
        <span class="save-icon"><mat-icon aria-hidden="true">{{ listing.is_liked ? 'favorite' : 'favorite_border' }}</mat-icon></span>
      </button>
    </article>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    :host { display: block; min-width: 0; }
    .listing-card {
      position: relative; height: 100%; overflow: hidden; box-sizing: border-box;
      background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
      transition: border-color var(--motion-fast);
    }
    .listing-card:hover { border-color: var(--border-strong); }
    .card-link { display: block; height: 100%; color: inherit; text-decoration: none; }
    .card-link:hover { color: inherit; text-decoration: none; }
    .card-link:focus-visible { outline-offset: -2px; border-radius: var(--radius-lg); }
    .media { position: relative; aspect-ratio: 16 / 9; background: var(--surface-2); border-bottom: 1px solid var(--border); }
    .media img { display: block; width: 100%; height: 100%; object-fit: cover; }
    .status {
      position: absolute; top: var(--space-2); left: var(--space-2); padding: 2px 8px;
      font-size: var(--font-size-xs); font-weight: 600; color: var(--text-primary);
      background: var(--surface); border: 1px solid var(--border); border-radius: 6px;
    }
    .info { display: flex; flex-direction: column; gap: 2px; min-width: 0; padding: var(--space-3); }
    .title {
      overflow: hidden; font-size: var(--font-size-base); font-weight: 600; color: var(--text-primary);
      text-overflow: ellipsis; white-space: nowrap;
    }
    .price-row { display: flex; align-items: baseline; justify-content: space-between; gap: var(--space-2); }
    .price { font-size: var(--font-size-base); font-weight: 600; color: var(--text-primary); white-space: nowrap; }
    .meta { font-size: var(--font-size-xs); color: var(--text-muted); white-space: nowrap; }
    .line { overflow: hidden; text-overflow: ellipsis; }
    .save {
      position: absolute; top: 0; right: 0; display: flex; align-items: center; justify-content: center;
      width: var(--touch-target); height: var(--touch-target); padding: 0; cursor: pointer; background: none; border: 0;
    }
    .save-icon {
      display: flex; align-items: center; justify-content: center; width: 30px; height: 30px;
      color: var(--text-primary); background: var(--surface); border: 1px solid var(--border); border-radius: 50%;
    }
    .save-icon mat-icon { width: 18px; height: 18px; font-size: 18px; }
    .save:hover .save-icon { background: var(--surface-2); }
    .save.saved .save-icon { color: var(--primary); }
    @media (max-width: 600px) {
      .media { aspect-ratio: 4 / 3; }
      .info { padding: 10px; }
      .title, .price { font-size: var(--font-size-sm); }
    }
  `]
})
export class ListingCardComponent {
  @Input({ required: true }) listing!: Listing;
  /** Emits the new saved state after the heart button is used. */
  @Output() savedChange = new EventEmitter<boolean>();
  saving = false;

  constructor(private api: ApiService, private auth: AuthService, private snackBar: MatSnackBar) {}

  /** Same rule as the listing page: sellers can't save their own listing. */
  get isMine(): boolean {
    return this.listing.seller?.id === this.auth.currentUser?.id;
  }

  get saveLabel(): string {
    const title = this.listing.title;
    return this.listing.is_liked
      ? $localize`:@@marketplace.card.unsave:Remove ${title}:title: from saved`
      : $localize`:@@marketplace.card.save:Save ${title}:title:`;
  }

  toggleSave(): void {
    if (this.saving) return;
    this.saving = true;
    this.api.likeListing(this.listing.id).subscribe({
      next: (res) => {
        this.saving = false;
        this.listing.is_liked = res.liked;
        this.listing.likes_count += res.liked ? 1 : -1;
        this.savedChange.emit(res.liked);
      },
      error: () => {
        this.saving = false;
        this.snackBar.open($localize`:@@marketplace.card.saveFailed:Could not update your saved listings`,
          $localize`:@@marketplace.dismiss:Dismiss`, { duration: 3000 });
      },
    });
  }

  get image(): string {
    return primaryImage(this.listing);
  }

  get conditionLabel(): string {
    return LISTING_CONDITIONS.find((c) => c.value === this.listing.condition)?.label ?? this.listing.condition;
  }
}
