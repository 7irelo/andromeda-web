import { Component, Input, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../../core/services/api.service';
import { Listing } from '../../../models/listing.model';

@Component({
  selector: 'app-listing-detail',
  standalone: true,
  imports: [CommonModule, RouterLink, MatButtonModule, MatIconModule, MatProgressSpinnerModule],
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
          <span class="badge" [ngClass]="'badge-' + listing.condition">{{ listing.condition | titlecase }}</span>
          <span class="text-secondary" *ngIf="listing.location">{{ listing.location }}</span>
        </p>
        <p class="description">{{ listing.description }}</p>

        <div class="listing-stats">
          <span class="text-secondary text-sm"><mat-icon class="stat-icon">visibility</mat-icon> {{ listing.views_count }} views</span>
          <span class="text-secondary text-sm"><mat-icon class="stat-icon">favorite</mat-icon> {{ listing.likes_count }} likes</span>
        </div>

        <div class="seller-card" *ngIf="listing.seller">
          <a [routerLink]="'/profile/' + listing.seller.username" class="seller-link">
            <img [src]="listing.seller.avatar_url || 'assets/default-avatar.png'" class="avatar md" [alt]="listing.seller.username" />
            <div>
              <div class="font-semibold">{{ listing.seller.full_name }}</div>
              <div class="text-secondary text-sm">&#64;{{ listing.seller.username }}</div>
            </div>
          </a>
        </div>

        <div class="action-buttons">
          <button mat-flat-button color="primary" class="message-btn">
            <mat-icon>chat</mat-icon> Message Seller
          </button>
          <button mat-stroked-button (click)="toggleLike()" [class.liked]="listing.is_liked">
            <mat-icon>{{ listing.is_liked ? 'favorite' : 'favorite_border' }}</mat-icon>
            {{ listing.is_liked ? 'Saved' : 'Save' }}
          </button>
        </div>
      </div>
    </div>

    <div class="loading-center" *ngIf="!listing">
      <mat-spinner diameter="40"></mat-spinner>
    </div>
  `,
  styles: [`
    .listing-detail {
      display: grid; grid-template-columns: 1fr 1fr; gap: 32px;
      max-width: 960px; margin: 0 auto; padding: 24px 16px;
    }
    @media (max-width: 768px) { .listing-detail { grid-template-columns: 1fr; } }
    .main-img { width: 100%; border-radius: 12px; object-fit: cover; max-height: 420px; }
    .thumb-row { display: flex; gap: 8px; margin-top: 10px; }
    .thumb {
      width: 64px; height: 64px; object-fit: cover; border-radius: 8px;
      cursor: pointer; border: 2px solid transparent; transition: border-color .2s;
    }
    .thumb.active { border-color: var(--primary); }
    .thumb:hover { border-color: var(--primary); }
    .listing-info { display: flex; flex-direction: column; gap: 12px; }
    .price { font-size: 32px; font-weight: 800; color: var(--primary); }
    h1 { font-size: 22px; font-weight: 700; margin: 0; }
    .condition-location { display: flex; align-items: center; gap: 10px; }
    .badge { padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; }
    .badge-new { background: #dcfce7; color: #16a34a; }
    .badge-like_new { background: #e0f2fe; color: #0284c7; }
    .badge-good { background: var(--primary-light); color: var(--primary); }
    .badge-fair { background: #fef3c7; color: #d97706; }
    .badge-poor { background: #fee2e2; color: #dc2626; }
    .description { color: var(--text-secondary); line-height: 1.6; }
    .listing-stats { display: flex; gap: 16px; align-items: center; }
    .stat-icon { font-size: 16px; width: 16px; height: 16px; vertical-align: middle; margin-right: 4px; }
    .seller-card {
      background: var(--surface-2); border: 1px solid var(--border); border-radius: 12px; padding: 12px 16px;
    }
    .seller-link { display: flex; align-items: center; gap: 12px; text-decoration: none; color: inherit; }
    .seller-link:hover { text-decoration: none; }
    .action-buttons { display: flex; gap: 10px; margin-top: 4px; }
    .message-btn { flex: 1; }
    .liked { color: var(--danger); border-color: var(--danger); }
    .loading-center { display: flex; justify-content: center; padding: 60px; }
  `]
})
export class ListingDetailComponent implements OnInit {
  @Input() id!: string;
  listing: Listing | null = null;
  currentImage = '';

  constructor(private apiService: ApiService) {}

  ngOnInit(): void {
    this.apiService.getListing(Number(this.id)).subscribe((l) => {
      this.listing = l;
      this.currentImage = l.images.find(i => i.is_primary)?.image || l.images[0]?.image || 'assets/default-listing.png';
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
