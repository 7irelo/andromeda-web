import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule, ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../core/services/api.service';
import { Listing } from '../../models/listing.model';

@Component({
  selector: 'app-marketplace',
  standalone: true,
  imports: [
    CommonModule, RouterLink, FormsModule, ReactiveFormsModule,
    MatIconModule, MatButtonModule, MatInputModule, MatProgressSpinnerModule,
    MatFormFieldModule, MatSelectModule, MatSnackBarModule,
  ],
  templateUrl: './marketplace.component.html',
  styleUrls: ['./marketplace.component.scss'],
})
export class MarketplaceComponent implements OnInit {
  listings: Listing[] = [];
  loading = false;
  searchQuery = '';

  isCreating = false;
  saving = false;
  createForm!: FormGroup;

  readonly conditions = [
    { value: 'new', label: 'New' },
    { value: 'like_new', label: 'Like New' },
    { value: 'good', label: 'Good' },
    { value: 'fair', label: 'Fair' },
    { value: 'poor', label: 'Poor' },
  ];

  constructor(
    private apiService: ApiService,
    private fb: FormBuilder,
    private snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void { this.load(); }

  load(): void {
    this.loading = true;
    const params = this.searchQuery ? { search: this.searchQuery } : undefined;
    this.apiService.getListings(params).subscribe({
      next: (res) => {
        this.listings = res.results;
        this.loading = false;
      },
      error: () => (this.loading = false),
    });
  }

  primaryImage(listing: Listing): string {
    const primary = listing.images?.find((i) => i.is_primary);
    return primary?.image || listing.images?.[0]?.image || 'assets/default-listing.png';
  }

  openCreateDialog(): void {
    this.createForm = this.fb.group({
      title: ['', Validators.required],
      description: ['', Validators.required],
      price: ['', [Validators.required, Validators.min(0)]],
      currency: ['USD'],
      condition: ['good', Validators.required],
      location: [''],
    });
    this.isCreating = true;
  }

  saveCreate(): void {
    if (this.createForm.invalid || this.saving) return;
    this.saving = true;
    this.apiService.createListing(this.createForm.value).subscribe({
      next: () => {
        this.isCreating = false;
        this.saving = false;
        this.snackBar.open('Listing created!', 'Dismiss', { duration: 3000 });
        this.load();
      },
      error: () => {
        this.saving = false;
        this.snackBar.open('Failed to create listing', 'Dismiss', { duration: 3000 });
      },
    });
  }

  cancelCreate(): void {
    this.isCreating = false;
  }
}
