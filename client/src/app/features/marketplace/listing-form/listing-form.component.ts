import {
  Component, EventEmitter, Input, OnDestroy, OnInit, Output, ChangeDetectionStrategy,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { Observable, Subscription, of, switchMap } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../../core/services/api.service';
import { ComposeAssistComponent } from '../../../shared/components/compose-assist/compose-assist.component';
import {
  City, LISTING_CONDITIONS, Listing, ListingCategory, ListingStatus, PriceSuggestion,
} from '../../../models/listing.model';

const MAX_IMAGES = 10;
const MAX_DRAFT_IMAGES = 4;
const AI_FIELDS = ['title', 'description', 'category_id', 'condition'] as const;
type AiField = typeof AI_FIELDS[number];

/** Pull the first readable message out of a DRF error response. */
export function apiError(err: HttpErrorResponse, fallback: string): string {
  const body = err?.error;
  if (typeof body?.detail === 'string') return body.detail;
  if (body && typeof body === 'object') {
    const first = Object.values(body)[0];
    if (Array.isArray(first) && typeof first[0] === 'string') return first[0];
    if (typeof first === 'string') return first;
  }
  return fallback;
}

/**
 * Create or edit a listing. Includes the Listing Assistant: "Fill in from photos"
 * sends the chosen photos to the draft endpoint and pre-fills the form with
 * clearly marked, editable suggestions plus a price range from similar listings.
 */
@Component({
    selector: 'app-listing-form',
    imports: [
        CommonModule, ReactiveFormsModule, MatIconModule, MatButtonModule, MatInputModule, MatFormFieldModule,
        MatSelectModule, MatCheckboxModule, MatProgressSpinnerModule, MatSnackBarModule, ComposeAssistComponent,
    ],
    template: `
    <div class="edit-overlay" (click)="close()"></div>
    <div class="edit-dialog card" [formGroup]="form" role="dialog" aria-modal="true">
      <div class="edit-dialog-header">
        <h2>{{ listing ? 'Edit listing' : 'Create listing' }}</h2>
        <button mat-icon-button (click)="close()" aria-label="Close"><mat-icon>close</mat-icon></button>
      </div>

      <div class="edit-dialog-body">
        <!-- Photos -->
        <div class="photos">
          <div class="photo" *ngFor="let p of existingImages"><img [src]="p" alt="" /></div>
          <div class="photo" *ngFor="let p of previews; let i = index">
            <img [src]="p" alt="" />
            <button type="button" class="remove-photo" (click)="removePhoto(i)" aria-label="Remove photo">
              <mat-icon>close</mat-icon>
            </button>
          </div>
          <label class="photo add-photo" *ngIf="existingImages.length + files.length < maxImages">
            <mat-icon>add_a_photo</mat-icon>
            <span class="text-xs">Add photos</span>
            <input type="file" accept="image/jpeg,image/png,image/webp,image/gif" multiple hidden
                   (change)="addPhotos($event)" />
          </label>
        </div>

        <div class="assistant" *ngIf="!listing">
          <mat-form-field appearance="outline" class="w-full">
            <mat-label>Anything the photos don't show? (optional)</mat-label>
            <input matInput formControlName="hint" maxlength="500" placeholder="e.g. 128GB, bought 2024, comes with charger" />
          </mat-form-field>
          <button mat-stroked-button type="button" (click)="fillFromPhotos()" [disabled]="!files.length || drafting">
            <mat-icon *ngIf="!drafting">auto_awesome</mat-icon>
            <mat-spinner *ngIf="drafting" diameter="18"></mat-spinner>
            {{ drafting ? 'Looking at your photos…' : 'Fill in from photos' }}
          </button>
          <span class="text-xs text-secondary" *ngIf="!files.length">Add a photo first.</span>
          <p class="ai-note text-xs" *ngIf="aiFields.size">
            <mat-icon>auto_awesome</mat-icon>
            Fields marked AI-suggested were filled in from your photos. Check them before you post.
          </p>
        </div>

        <mat-form-field appearance="outline" class="w-full">
          <mat-label>Title</mat-label>
          <input matInput formControlName="title" maxlength="255" placeholder="What are you selling?" />
          <span matSuffix class="ai-chip" *ngIf="aiFields.has('title')">AI-suggested</span>
        </mat-form-field>

        <mat-form-field appearance="outline" class="w-full">
          <mat-label>Description</mat-label>
          <textarea matInput formControlName="description" rows="4" placeholder="Describe your item..."></textarea>
          <mat-hint *ngIf="aiFields.has('description')" class="ai-chip">AI-suggested</mat-hint>
        </mat-form-field>
        <app-compose-assist [text]="form.value.description" kind="listing"
                            (accepted)="form.patchValue({ description: $event })"></app-compose-assist>

        <div class="edit-row">
          <mat-form-field appearance="outline" class="w-full">
            <mat-label>Category</mat-label>
            <mat-select formControlName="category_id">
              <mat-option [value]="null">None</mat-option>
              <mat-optgroup *ngFor="let top of categories" [label]="top.name">
                <mat-option [value]="top.id">All {{ top.name }}</mat-option>
                <mat-option *ngFor="let child of top.children" [value]="child.id">{{ child.name }}</mat-option>
              </mat-optgroup>
            </mat-select>
            <mat-hint *ngIf="aiFields.has('category_id')" class="ai-chip">AI-suggested</mat-hint>
          </mat-form-field>
          <mat-form-field appearance="outline" class="w-full">
            <mat-label>Condition</mat-label>
            <mat-select formControlName="condition">
              <mat-option *ngFor="let c of conditions" [value]="c.value">{{ c.label }}</mat-option>
            </mat-select>
            <mat-hint *ngIf="aiFields.has('condition')" class="ai-chip">AI-suggested</mat-hint>
          </mat-form-field>
        </div>

        <div class="price-suggestion" *ngIf="suggestion">
          <mat-icon>insights</mat-icon>
          <div>
            <div class="font-semibold">
              Similar items go for {{ suggestion.currency }} {{ suggestion.low | number:'1.0-0' }}
              – {{ suggestion.high | number:'1.0-0' }}
            </div>
            <div class="text-xs text-secondary">
              Median {{ suggestion.currency }} {{ suggestion.median | number:'1.0-0' }}, based on
              {{ suggestion.based_on }} similar listing{{ suggestion.based_on === 1 ? '' : 's' }}.
            </div>
          </div>
          <button mat-button type="button" (click)="useMedian()">Use median</button>
        </div>
        <p class="text-xs text-secondary" *ngIf="drafted && !suggestion">
          Not enough similar listings yet to suggest a price.
        </p>

        <div class="edit-row">
          <mat-form-field appearance="outline" class="w-full">
            <mat-label>Price</mat-label>
            <input matInput type="number" min="0" formControlName="price" placeholder="0.00" />
          </mat-form-field>
          <mat-form-field appearance="outline" class="w-full">
            <mat-label>Currency</mat-label>
            <input matInput formControlName="currency" maxlength="3" />
          </mat-form-field>
        </div>

        <mat-form-field appearance="outline" class="w-full">
          <mat-label>Location</mat-label>
          <mat-icon matPrefix>location_on</mat-icon>
          <input matInput formControlName="location" placeholder="Suburb, City" list="listing-cities" />
          <datalist id="listing-cities">
            <option *ngFor="let c of cities" [value]="c.name"></option>
          </datalist>
          <mat-hint>Buyers see the area, never your exact position.</mat-hint>
        </mat-form-field>

        <mat-checkbox [checked]="!!point" (change)="togglePreciseLocation($event.checked)" [disabled]="locating">
          Use my current location for distance search (rounded to about 1 km)
        </mat-checkbox>

        <mat-form-field appearance="outline" class="w-full" *ngIf="listing">
          <mat-label>Status</mat-label>
          <mat-select formControlName="status">
            <mat-option *ngFor="let s of statuses" [value]="s.value">{{ s.label }}</mat-option>
          </mat-select>
        </mat-form-field>
      </div>

      <div class="edit-dialog-actions">
        <button mat-stroked-button (click)="close()" [disabled]="saving">Cancel</button>
        <button mat-flat-button color="primary" (click)="save()" [disabled]="saving || form.invalid">
          <mat-icon *ngIf="!saving">{{ listing ? 'save' : 'add' }}</mat-icon>
          <mat-spinner *ngIf="saving" diameter="18"></mat-spinner>
          {{ saving ? 'Saving…' : (listing ? 'Save changes' : 'Create listing') }}
        </button>
      </div>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    .edit-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.45); z-index: 100; backdrop-filter: blur(2px); }
    .edit-dialog {
      position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 101;
      width: min(600px, 95vw); max-height: 92vh; overflow-y: auto; padding: 0;
    }
    .edit-dialog-header {
      display: flex; align-items: center; justify-content: space-between; padding: 20px 24px 16px;
      border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--surface); z-index: 2;
    }
    .edit-dialog-header h2 { font-size: 18px; font-weight: 700; margin: 0; }
    .edit-dialog-body { padding: 20px 24px; display: flex; flex-direction: column; gap: 8px; }
    .edit-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    @media (max-width: 520px) { .edit-row { grid-template-columns: 1fr; } }
    .edit-dialog-actions {
      display: flex; justify-content: flex-end; gap: 10px; padding: 16px 24px; border-top: 1px solid var(--border);
      position: sticky; bottom: 0; background: var(--surface);
    }
    .w-full { width: 100%; }
    .photos { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
    .photo {
      position: relative; width: 84px; height: 84px; border-radius: 10px; overflow: hidden;
      border: 1px solid var(--border); background: var(--surface-2);
    }
    .photo img { width: 100%; height: 100%; object-fit: cover; }
    .add-photo {
      display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px;
      cursor: pointer; color: var(--primary); border-style: dashed;
    }
    .remove-photo {
      position: absolute; top: 2px; right: 2px; border: 0; border-radius: 50%; width: 22px; height: 22px;
      background: rgba(0,0,0,.6); color: #fff; cursor: pointer; display: flex; align-items: center;
      justify-content: center; padding: 0;
    }
    .remove-photo mat-icon { font-size: 14px; width: 14px; height: 14px; }
    .assistant {
      display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; padding: 12px;
      border: 1px dashed var(--primary); border-radius: 12px; margin-bottom: 8px;
    }
    .assistant mat-form-field { flex-basis: 100%; }
    .ai-note { display: flex; align-items: center; gap: 4px; margin: 0; flex-basis: 100%; color: var(--primary); }
    .ai-note mat-icon { font-size: 14px; width: 14px; height: 14px; }
    .ai-chip {
      font-size: 11px; font-weight: 600; color: var(--primary); background: var(--primary-light);
      padding: 2px 8px; border-radius: 999px; margin-right: 8px; white-space: nowrap;
    }
    .price-suggestion {
      display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-radius: 10px;
      background: var(--primary-light); margin-bottom: 8px;
    }
    .price-suggestion > div { flex: 1; }
    .price-suggestion mat-icon { color: var(--primary); }
  `]
})
export class ListingFormComponent implements OnInit, OnDestroy {
  /** The listing to edit; omit to create a new one. */
  @Input() listing: Listing | null = null;
  @Input() categories: ListingCategory[] = [];
  @Input() cities: City[] = [];
  @Output() saved = new EventEmitter<Listing>();
  @Output() closed = new EventEmitter<void>();

  readonly conditions = LISTING_CONDITIONS;
  readonly maxImages = MAX_IMAGES;
  readonly statuses: { value: ListingStatus; label: string }[] = [
    { value: 'active', label: 'Active' }, { value: 'reserved', label: 'Reserved' },
    { value: 'sold', label: 'Sold' }, { value: 'draft', label: 'Draft (only you can see it)' },
  ];

  form!: FormGroup;
  files: File[] = [];
  previews: string[] = [];
  existingImages: string[] = [];
  aiFields = new Set<AiField>();
  suggestion: PriceSuggestion | null = null;
  drafted = false;
  drafting = false;
  saving = false;
  locating = false;
  point: { latitude: number; longitude: number } | null = null;

  private subs: Subscription[] = [];
  /** Set while the assistant fills the form, so its own writes don't clear the AI markers. */
  private filling = false;

  constructor(private api: ApiService, private fb: FormBuilder, private snackBar: MatSnackBar) {}

  ngOnInit(): void {
    const l = this.listing;
    this.form = this.fb.group({
      title: [l?.title ?? '', [Validators.required, Validators.maxLength(255)]],
      description: [l?.description ?? '', Validators.required],
      price: [l?.price ?? '', [Validators.required, Validators.min(0)]],
      currency: [l?.currency ?? 'ZAR', [Validators.required, Validators.pattern(/^[A-Za-z]{3}$/)]],
      condition: [l?.condition ?? 'good', Validators.required],
      category_id: [l?.category?.id ?? null],
      location: [l?.location ?? ''],
      status: [l?.status ?? 'active'],
      hint: [''],
    });
    this.existingImages = (l?.images ?? []).map((i) => i.image);
    // Editing a suggested field makes it the seller's own.
    for (const field of AI_FIELDS) {
      this.subs.push(this.form.get(field)!.valueChanges.subscribe(() => {
        if (!this.filling) this.aiFields.delete(field);
      }));
    }
  }

  ngOnDestroy(): void {
    this.subs.forEach((s) => s.unsubscribe());
    this.previews.forEach((p) => URL.revokeObjectURL(p));
  }

  addPhotos(event: Event): void {
    const input = event.target as HTMLInputElement;
    const room = MAX_IMAGES - this.existingImages.length - this.files.length;
    const chosen = Array.from(input.files ?? []).filter((f) => f.type.startsWith('image/')).slice(0, room);
    this.files.push(...chosen);
    this.previews.push(...chosen.map((f) => URL.createObjectURL(f)));
    input.value = '';
  }

  removePhoto(i: number): void {
    URL.revokeObjectURL(this.previews[i]);
    this.files.splice(i, 1);
    this.previews.splice(i, 1);
  }

  fillFromPhotos(): void {
    if (!this.files.length || this.drafting) return;
    const data = new FormData();
    this.files.slice(0, MAX_DRAFT_IMAGES).forEach((f) => data.append('images', f));
    const hint = (this.form.value.hint ?? '').trim();
    if (hint) data.append('hint', hint);
    data.append('currency', (this.form.value.currency || 'ZAR').toUpperCase());
    this.drafting = true;
    this.api.draftListing(data).subscribe({
      next: (draft) => {
        this.filling = true;
        const patch: Record<string, unknown> = {};
        if (draft.title) { patch['title'] = draft.title; this.aiFields.add('title'); }
        if (draft.description) { patch['description'] = draft.description; this.aiFields.add('description'); }
        if (draft.category) { patch['category_id'] = draft.category.id; this.aiFields.add('category_id'); }
        if (draft.condition) { patch['condition'] = draft.condition; this.aiFields.add('condition'); }
        this.form.patchValue(patch);
        this.filling = false;
        this.suggestion = draft.price_suggestion;
        this.drafted = true;
        this.drafting = false;
      },
      error: (err: HttpErrorResponse) => {
        this.drafting = false;
        this.snackBar.open(apiError(err, 'The listing assistant is not available right now.'), 'Dismiss',
          { duration: 4000 });
      },
    });
  }

  useMedian(): void {
    if (this.suggestion) this.form.patchValue({ price: Math.round(this.suggestion.median) });
  }

  togglePreciseLocation(on: boolean): void {
    if (!on) { this.point = null; return; }
    if (!('geolocation' in navigator)) {
      this.snackBar.open('Your browser cannot share a location.', 'Dismiss', { duration: 3000 });
      return;
    }
    this.locating = true;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        this.point = { latitude: pos.coords.latitude, longitude: pos.coords.longitude };
        this.locating = false;
      },
      () => {
        this.point = null;
        this.locating = false;
        this.snackBar.open('Location permission was not given.', 'Dismiss', { duration: 3000 });
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 },
    );
  }

  save(): void {
    if (this.form.invalid || this.saving) return;
    const v = this.form.value;
    const fields: Record<string, unknown> = {
      title: v.title, description: v.description, price: v.price, currency: String(v.currency).toUpperCase(),
      condition: v.condition, location: v.location ?? '',
    };
    if (this.point) Object.assign(fields, this.point);
    this.saving = true;
    let request: Observable<Listing>;
    if (this.listing) {
      const id = this.listing.id;
      request = this.api.updateListing(id, { ...fields, category_id: v.category_id, status: v.status }).pipe(
        switchMap((updated) => {
          if (!this.files.length) return of(updated);
          const photos = new FormData();
          this.files.forEach((f) => photos.append('images', f));
          return this.api.uploadListingImages(id, photos).pipe(switchMap(() => this.api.getListing(id)));
        }),
      );
    } else {
      const data = new FormData();
      Object.entries(fields).forEach(([k, val]) => data.append(k, String(val)));
      if (v.category_id) data.append('category_id', String(v.category_id));
      this.files.forEach((f) => data.append('images', f));
      request = this.api.createListing(data);
    }
    request.subscribe({
      next: (listing) => {
        this.saving = false;
        this.snackBar.open(this.listing ? 'Listing updated' : 'Listing created!', 'Dismiss', { duration: 3000 });
        this.saved.emit(listing);
      },
      error: (err: HttpErrorResponse) => {
        this.saving = false;
        this.snackBar.open(apiError(err, 'Could not save the listing'), 'Dismiss', { duration: 4000 });
      },
    });
  }

  close(): void {
    if (!this.saving) this.closed.emit();
  }
}
