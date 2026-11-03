import {
  Component, EventEmitter, Input, OnDestroy, OnInit, Output, ChangeDetectionStrategy,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { Observable, Subscription, of, switchMap } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../../core/services/api.service';
import { ComposeAssistComponent } from '../../../shared/components/compose-assist/compose-assist.component';
import { ModalDialogDirective } from '../../../shared/a11y/modal-dialog.directive';
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
        CommonModule, ReactiveFormsModule, MatIconModule, MatProgressSpinnerModule, MatSnackBarModule, ComposeAssistComponent,
        ModalDialogDirective,
    ],
    template: `
    <div class="edit-overlay" (click)="close()"></div>
    <div class="edit-dialog card" [formGroup]="form" appModalDialog
         [dialogLabel]="listing ? 'Edit listing' : 'Create listing'" (dismiss)="close()">
      <div class="edit-dialog-header">
        <h2>{{ listing ? 'Edit listing' : 'Create listing' }}</h2>
        <button class="ui-icon-btn" type="button" (click)="close()" aria-label="Close"><mat-icon aria-hidden="true">close</mat-icon></button>
      </div>

      <div class="edit-dialog-body">
        <!-- Photos -->
        <div class="photos">
          <div class="photo" *ngFor="let p of existingImages"><img [src]="p" alt="" /></div>
          <div class="photo" *ngFor="let p of previews; let i = index">
            <img [src]="p" alt="" />
            <button type="button" class="remove-photo" (click)="removePhoto(i)" aria-label="Remove photo">
              <span class="remove-icon"><mat-icon aria-hidden="true">close</mat-icon></span>
            </button>
          </div>
          <label class="photo add-photo" *ngIf="existingImages.length + files.length < maxImages">
            <mat-icon aria-hidden="true">add_a_photo</mat-icon>
            <span class="text-xs">Add photos</span>
            <input type="file" class="visually-hidden" accept="image/jpeg,image/png,image/webp,image/gif" multiple
                   (change)="addPhotos($event)" />
          </label>
        </div>

        <div class="assistant" *ngIf="!listing">
          <label class="ui-field">
            Anything the photos don't show? (optional)
            <input class="ui-control" formControlName="hint" maxlength="500" placeholder="e.g. 128GB, bought 2024, comes with charger" />
          </label>
          <div class="assistant-action">
            <button class="ui-btn" type="button" (click)="fillFromPhotos()" [disabled]="!files.length || drafting">
              <mat-icon *ngIf="!drafting" aria-hidden="true">auto_awesome</mat-icon>
              <mat-spinner *ngIf="drafting" diameter="18"></mat-spinner>
              {{ drafting ? 'Looking at your photos…' : 'Fill in from photos' }}
            </button>
            <span class="text-xs text-secondary" *ngIf="!files.length">Add a photo first.</span>
          </div>
          <p class="ai-note text-xs" *ngIf="aiFields.size">
            <mat-icon aria-hidden="true">auto_awesome</mat-icon>
            Fields marked AI-suggested were filled in from your photos. Check them before you post.
          </p>
        </div>

        <label class="ui-field">
          <span class="field-label">Title *<span class="ai-chip" *ngIf="aiFields.has('title')">AI-suggested</span></span>
          <input class="ui-control" formControlName="title" maxlength="255" placeholder="What are you selling?"
                 aria-required="true" [attr.aria-invalid]="invalid('title')" />
        </label>

        <label class="ui-field">
          <span class="field-label">Description *<span class="ai-chip" *ngIf="aiFields.has('description')">AI-suggested</span></span>
          <textarea class="ui-control" formControlName="description" rows="4" placeholder="Describe your item..."
                    aria-required="true" [attr.aria-invalid]="invalid('description')"></textarea>
        </label>
        <app-compose-assist [text]="form.value.description" kind="listing"
                            (accepted)="form.patchValue({ description: $event })"></app-compose-assist>

        <div class="edit-row">
          <label class="ui-field">
            <span class="field-label">Category<span class="ai-chip" *ngIf="aiFields.has('category_id')">AI-suggested</span></span>
            <select class="ui-control" formControlName="category_id">
              <option [ngValue]="null">None</option>
              <optgroup *ngFor="let top of categories" [label]="top.name">
                <option [ngValue]="top.id">All {{ top.name }}</option>
                <option *ngFor="let child of top.children" [ngValue]="child.id">{{ child.name }}</option>
              </optgroup>
            </select>
          </label>
          <label class="ui-field">
            <span class="field-label">Condition *<span class="ai-chip" *ngIf="aiFields.has('condition')">AI-suggested</span></span>
            <select class="ui-control" formControlName="condition" aria-required="true">
              <option *ngFor="let c of conditions" [ngValue]="c.value">{{ c.label }}</option>
            </select>
          </label>
        </div>

        <div class="price-suggestion" *ngIf="suggestion">
          <mat-icon aria-hidden="true">insights</mat-icon>
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
          <button class="ui-btn" type="button" (click)="useMedian()">Use median</button>
        </div>
        <p class="drafted-note text-xs text-secondary" *ngIf="drafted && !suggestion">
          Not enough similar listings yet to suggest a price.
        </p>

        <div class="edit-row">
          <label class="ui-field">
            Price *
            <input class="ui-control" type="number" min="0" formControlName="price" placeholder="0.00"
                   aria-required="true" [attr.aria-invalid]="invalid('price')" />
          </label>
          <label class="ui-field">
            Currency *
            <input class="ui-control" formControlName="currency" maxlength="3"
                   aria-required="true" [attr.aria-invalid]="invalid('currency')" />
          </label>
        </div>

        <label class="ui-field">
          Location
          <input class="ui-control" formControlName="location" placeholder="Suburb, City" list="listing-cities"
                 aria-describedby="listing-location-hint" />
          <datalist id="listing-cities">
            <option *ngFor="let c of cities" [value]="c.name"></option>
          </datalist>
        </label>
        <span class="field-hint" id="listing-location-hint">Buyers see the area, never your exact position.</span>

        <label class="ui-check">
          <input type="checkbox" [checked]="!!point" (change)="togglePreciseLocation($any($event.target).checked)" [disabled]="locating" />
          Use my current location for distance search (rounded to about 1 km)
        </label>

        <label class="ui-field" *ngIf="listing">
          Status
          <select class="ui-control" formControlName="status">
            <option *ngFor="let s of statuses" [ngValue]="s.value">{{ s.label }}</option>
          </select>
        </label>
      </div>

      <div class="edit-dialog-actions">
        <button class="ui-btn" type="button" (click)="close()" [disabled]="saving">Cancel</button>
        <button class="ui-btn ui-btn-primary" type="button" (click)="save()" [disabled]="saving || form.invalid">
          <mat-icon *ngIf="!saving" aria-hidden="true">{{ listing ? 'save' : 'add' }}</mat-icon>
          <mat-spinner *ngIf="saving" diameter="18"></mat-spinner>
          {{ saving ? 'Saving…' : (listing ? 'Save changes' : 'Create listing') }}
        </button>
      </div>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styleUrls: ['../ui.scss'],
    styles: [`
    .edit-overlay { position: fixed; inset: 0; z-index: 100; background: rgba(0, 0, 0, .45); }
    .edit-dialog {
      position: fixed; top: 50%; left: 50%; z-index: 101; transform: translate(-50%, -50%);
      box-sizing: border-box; width: min(600px, calc(100vw - 16px)); max-height: 92vh; padding: 0; overflow-y: auto;
    }
    .edit-dialog-header {
      position: sticky; top: 0; z-index: 2; display: flex; align-items: center; justify-content: space-between;
      padding: var(--space-3) var(--space-3) var(--space-3) var(--space-5);
      background: var(--surface); border-bottom: 1px solid var(--border);
    }
    .edit-dialog-header h2 { margin: 0; font-size: var(--font-size-lg); font-weight: 600; }
    .edit-dialog-body { display: flex; flex-direction: column; gap: var(--space-3); padding: var(--space-4) var(--space-5); }
    .edit-row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-3); }
    .edit-dialog-actions {
      position: sticky; bottom: 0; display: flex; justify-content: flex-end; gap: var(--space-2);
      padding: var(--space-3) var(--space-5); background: var(--surface); border-top: 1px solid var(--border);
    }
    .field-label { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); }
    .field-hint { margin-top: calc(var(--space-2) * -1); font-size: var(--font-size-xs); color: var(--text-muted); }
    .drafted-note { margin: 0; }
    .photos { display: flex; flex-wrap: wrap; gap: var(--space-2); }
    .photo {
      position: relative; box-sizing: border-box; width: 84px; height: 84px; overflow: hidden;
      background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm);
    }
    .photo img { display: block; width: 100%; height: 100%; object-fit: cover; }
    .add-photo {
      display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px;
      color: var(--primary); cursor: pointer; border: 1px dashed var(--border-strong);
    }
    .add-photo:focus-within { outline: 2px solid var(--focus-ring-color); outline-offset: 2px; }
    .remove-photo {
      position: absolute; top: 0; right: 0; display: flex; align-items: flex-start; justify-content: flex-end;
      width: var(--touch-target); height: var(--touch-target); padding: var(--space-1); cursor: pointer; background: none; border: 0;
    }
    .remove-icon {
      display: flex; align-items: center; justify-content: center; width: 22px; height: 22px;
      color: var(--text-primary); background: var(--surface); border: 1px solid var(--border); border-radius: 50%;
    }
    .remove-icon mat-icon { width: 14px; height: 14px; font-size: 14px; }
    .assistant {
      display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-3);
      background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-md);
    }
    .assistant-action { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2) var(--space-3); }
    .ai-note { display: flex; align-items: center; gap: var(--space-1); margin: 0; color: var(--primary); }
    .ai-note mat-icon { flex: none; width: 14px; height: 14px; font-size: 14px; }
    .ai-chip {
      padding: 1px 6px; font-size: 11px; font-weight: 600; color: var(--primary); white-space: nowrap;
      background: var(--primary-light); border-radius: 6px;
    }
    .price-suggestion {
      display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2) var(--space-3); padding: var(--space-3);
      font-size: var(--font-size-sm); background: var(--primary-light); border-radius: var(--radius-md);
    }
    .price-suggestion > div { flex: 1 1 180px; min-width: 0; }
    .price-suggestion mat-icon { color: var(--primary); }
    .price-suggestion .ui-btn mat-icon { color: inherit; }
    @media (max-width: 600px) {
      .edit-dialog-header { padding-left: var(--space-4); }
      .edit-dialog-body { padding: var(--space-4); }
      .edit-dialog-actions { padding: var(--space-3) var(--space-4); }
      .edit-row { grid-template-columns: minmax(0, 1fr); }
      .edit-dialog-actions .ui-btn { flex: 1; }
    }
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

  /** For aria-invalid: only once the user has been in the field, as Material did. */
  invalid(name: string): boolean {
    const control = this.form.get(name);
    return !!control && control.invalid && control.touched;
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
