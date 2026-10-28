import { Component, Input, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { Listing, LISTING_CONDITIONS } from '../../../models/listing.model';

export function primaryImage(listing: Listing): string {
  const primary = listing.images?.find((i) => i.is_primary);
  return primary?.image || listing.images?.[0]?.image || 'assets/default-listing.png';
}

@Component({
    selector: 'app-listing-card',
    imports: [CommonModule, RouterLink, MatIconModule],
    template: `
    <a class="listing-card card" [routerLink]="'/marketplace/' + listing.id">
      <div class="listing-image">
        <img [src]="image" [alt]="listing.title" />
        <span class="condition-badge" [class]="'condition-' + listing.condition">{{ conditionLabel }}</span>
        <span class="status-badge" *ngIf="listing.status !== 'active'">{{ listing.status | titlecase }}</span>
      </div>
      <div class="listing-info">
        <div class="listing-price">{{ listing.currency }} {{ listing.price }}</div>
        <div class="listing-title font-medium">{{ listing.title }}</div>
        <div class="listing-meta text-secondary text-xs">
          <mat-icon>location_on</mat-icon>
          <span>{{ listing.location || 'Location not specified' }}</span>
          <span *ngIf="listing.distance_km !== null && listing.distance_km !== undefined">· ~{{ listing.distance_km }} km</span>
        </div>
        <div class="listing-meta text-secondary text-xs" *ngIf="listing.seller_rating?.count">
          <mat-icon class="star">star</mat-icon>
          <span>{{ listing.seller_rating.average | number:'1.1-1' }} seller ({{ listing.seller_rating.count }})</span>
        </div>
      </div>
    </a>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    :host { display: block; }
    .listing-card {
      display: block; height: 100%; text-decoration: none; color: inherit; overflow: hidden;
      border-radius: var(--border-radius); background: var(--surface); border: 1px solid var(--border);
      box-shadow: var(--shadow-sm); transition: transform .2s, box-shadow .2s;
    }
    .listing-card:hover { transform: translateY(-3px); box-shadow: var(--shadow-md); text-decoration: none; }
    .listing-image { height: 200px; overflow: hidden; position: relative; background: var(--surface-2); }
    .listing-image img { width: 100%; height: 100%; object-fit: cover; transition: transform .3s; }
    .listing-image:hover img { transform: scale(1.04); }
    .condition-badge, .status-badge {
      position: absolute; top: 10px; padding: 3px 10px; border-radius: 999px; font-size: 11px; font-weight: 700;
      text-transform: uppercase; letter-spacing: .4px; backdrop-filter: blur(6px); color: #fff;
    }
    .condition-badge { left: 10px; }
    .condition-new { background: rgba(34,197,94,.85); }
    .condition-like_new { background: rgba(6,182,212,.85); }
    .condition-good { background: rgba(79,70,229,.85); }
    .condition-fair { background: rgba(245,158,11,.85); }
    .condition-poor { background: rgba(100,116,139,.85); }
    .status-badge { right: 10px; background: rgba(217,119,6,.9); }
    .listing-info { padding: 14px; display: flex; flex-direction: column; gap: 5px; }
    .listing-price { font-size: 20px; font-weight: 800; color: var(--primary); letter-spacing: -.5px; }
    .listing-title {
      font-size: 14px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      color: var(--text-primary);
    }
    .listing-meta { display: flex; align-items: center; gap: 3px; color: var(--text-muted); }
    .listing-meta mat-icon { font-size: 13px; width: 13px; height: 13px; }
    .star { color: #f59e0b; }
  `]
})
export class ListingCardComponent {
  @Input({ required: true }) listing!: Listing;

  get image(): string {
    return primaryImage(this.listing);
  }

  get conditionLabel(): string {
    return LISTING_CONDITIONS.find((c) => c.value === this.listing.condition)?.label ?? this.listing.condition;
  }
}
