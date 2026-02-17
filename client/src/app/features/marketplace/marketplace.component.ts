import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../core/services/api.service';

@Component({
  selector: 'app-marketplace',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule, MatIconModule, MatButtonModule, MatInputModule, MatProgressSpinnerModule],
  templateUrl: './marketplace.component.html',
  styleUrls: ['./marketplace.component.scss'],
})
export class MarketplaceComponent implements OnInit {
  listings: unknown[] = [];
  loading = false;
  searchQuery = '';

  constructor(private apiService: ApiService) {}

  ngOnInit(): void { this.load(); }

  load(): void {
    this.loading = true;
    const params = this.searchQuery ? { search: this.searchQuery } : undefined;
    this.apiService.getListings(params).subscribe({
      next: (res: unknown) => {
        this.listings = (res as { results: unknown[] }).results;
        this.loading = false;
      },
      error: () => (this.loading = false),
    });
  }

  asListing(l: unknown): { id: number; title: string; price: string; currency: string; condition: string; location: string; images: { image: string; is_primary: boolean }[]; seller: { username: string; full_name: string } } {
    return l as ReturnType<typeof this.asListing>;
  }

  primaryImage(l: unknown): string {
    const listing = this.asListing(l);
    const primary = listing.images?.find((i) => i.is_primary);
    return primary?.image || 'assets/default-listing.png';
  }
}
