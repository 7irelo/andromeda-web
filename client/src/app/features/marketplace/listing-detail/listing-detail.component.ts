import { Component, Input, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { environment } from '../../../../environments/environment';

@Component({
  selector: 'app-listing-detail',
  standalone: true,
  imports: [CommonModule, MatButtonModule, MatIconModule],
  template: `
    <div class="listing-detail" *ngIf="listing">
      <div class="listing-images">
        <img [src]="currentImage" alt="" class="main-img" />
        <div class="thumb-row">
          <img *ngFor="let img of asListing(listing).images" [src]="img.image" (click)="currentImage = img.image" class="thumb" />
        </div>
      </div>
      <div class="listing-info">
        <div class="price">{{ asListing(listing).price | currency }}</div>
        <h1>{{ asListing(listing).title }}</h1>
        <p class="text-secondary">{{ asListing(listing).condition | titlecase }} · {{ asListing(listing).location }}</p>
        <p>{{ asListing(listing).description }}</p>
        <div class="seller-info">
          <span class="text-secondary">Sold by</span>
          <strong>{{ asListing(listing).seller?.full_name }}</strong>
        </div>
        <button mat-flat-button color="primary" style="margin-top:16px">Message Seller</button>
      </div>
    </div>
  `,
  styles: [`.listing-detail{display:grid;grid-template-columns:1fr 1fr;gap:24px;max-width:900px;margin:0 auto;padding:16px} .main-img{width:100%;border-radius:8px;object-fit:cover;max-height:400px} .thumb-row{display:flex;gap:8px;margin-top:8px} .thumb{width:60px;height:60px;object-fit:cover;border-radius:4px;cursor:pointer} .price{font-size:28px;font-weight:700;margin-bottom:8px} .seller-info{display:flex;gap:8px;align-items:center;margin-top:12px}`]
})
export class ListingDetailComponent implements OnInit {
  @Input() id!: string;
  listing: unknown = null;
  currentImage = '';

  constructor(private http: HttpClient) {}

  ngOnInit(): void {
    this.http.get(`${environment.apiUrl}/marketplace/listings/${this.id}/`).subscribe((l) => {
      this.listing = l;
      const imgs = this.asListing(l).images;
      this.currentImage = imgs.find(i => i.is_primary)?.image || imgs[0]?.image || 'assets/default-listing.png';
    });
  }

  asListing(l: unknown): { title: string; price: string; description: string; condition: string; location: string; images: { image: string; is_primary: boolean }[]; seller: { full_name: string } | null } {
    return l as ReturnType<typeof this.asListing>;
  }
}
