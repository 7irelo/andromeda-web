import { Component, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../core/services/api.service';
import { Page } from '../../models/page.model';
import { EmptyStateComponent, ErrorStateComponent, SkeletonComponent } from '../../shared/components/states';
import { ModalDialogDirective } from '../../shared/a11y/modal-dialog.directive';

@Component({
    selector: 'app-pages',
    imports: [
        CommonModule, ReactiveFormsModule, RouterLink,
        MatIconModule, MatButtonModule, MatProgressSpinnerModule,
        MatFormFieldModule, MatInputModule, MatSnackBarModule,
        EmptyStateComponent, ErrorStateComponent, SkeletonComponent, ModalDialogDirective,
    ],
    template: `
    <div class="page ui-controls">
      <div class="page-head">
        <div>
          <h1>Pages</h1>
          <p>Discover and follow community pages</p>
        </div>
        <button mat-flat-button color="primary" (click)="openCreateDialog()">
          <mat-icon aria-hidden="true">add</mat-icon> Create Page
        </button>
      </div>

      <app-skeleton *ngIf="loading" variant="grid" [count]="6"></app-skeleton>
      <app-error-state *ngIf="!loading && loadError" (retry)="loadPages()"></app-error-state>

      <div class="card-grid list-grid" *ngIf="!loading && !loadError">
        <div class="item-card card" *ngFor="let p of pages">
          <div class="item-cover">
            <img *ngIf="p.cover_photo" [src]="p.cover_photo" alt="" />
          </div>
          <div class="item-body">
            <a [routerLink]="'/pages/' + p.id" tabindex="-1" aria-hidden="true"><img [src]="p.avatar || 'assets/default-avatar.png'" class="page-avatar" alt="" width="56" height="56" /></a>
            <a class="item-name page-name" [routerLink]="'/pages/' + p.id">
              {{ p.name }}
              <mat-icon class="verified" *ngIf="p.is_verified" aria-label="Verified">verified</mat-icon>
            </a>
            <div class="item-meta">{{ p.category || 'Community' }} · {{ p.followers_count | number }} followers</div>
            <p class="page-desc" *ngIf="p.description">{{ p.description }}</p>
            <div class="item-action">
              <button
                mat-flat-button
                *ngIf="!p.is_following"
                color="primary"
                (click)="follow(p)"
              >
                <mat-icon>add</mat-icon> Follow
              </button>
              <button
                mat-stroked-button
                *ngIf="p.is_following"
                (click)="unfollow(p)"
              >
                <mat-icon>check</mat-icon> Following
              </button>
            </div>
          </div>
        </div>
      </div>

      <app-empty-state *ngIf="!loading && !loadError && pages.length === 0" icon="auto_stories"
                       title="No pages yet" message="Create the first one!">
        <button mat-flat-button color="primary" type="button" (click)="openCreateDialog()">Create Page</button>
      </app-empty-state>
    </div>

    <!-- Create Dialog -->
    <div class="edit-overlay" *ngIf="isCreating" (click)="cancelCreate()"></div>
    <div class="edit-dialog card ui-controls" *ngIf="isCreating" [formGroup]="createForm"
         appModalDialog dialogLabel="Create Page" (dismiss)="cancelCreate()">
      <div class="edit-dialog-header">
        <h2>Create Page</h2>
        <button mat-icon-button (click)="cancelCreate()" aria-label="Close"><mat-icon>close</mat-icon></button>
      </div>
      <div class="edit-dialog-body">
        <mat-form-field appearance="outline" class="w-full">
          <mat-label>Page Name</mat-label>
          <input matInput formControlName="name" placeholder="Name your page" />
        </mat-form-field>
        <mat-form-field appearance="outline" class="w-full">
          <mat-label>Category</mat-label>
          <input matInput formControlName="category" placeholder="e.g. Technology, Music, Sports" />
        </mat-form-field>
        <mat-form-field appearance="outline" class="w-full">
          <mat-label>Description</mat-label>
          <textarea matInput formControlName="description" rows="3" placeholder="What is this page about?"></textarea>
        </mat-form-field>
      </div>
      <div class="edit-dialog-actions">
        <button mat-stroked-button (click)="cancelCreate()" [disabled]="saving">Cancel</button>
        <button mat-flat-button color="primary" (click)="saveCreate()" [disabled]="saving || createForm.invalid">
          <mat-spinner *ngIf="saving" diameter="18"></mat-spinner>
          {{ saving ? 'Creating...' : 'Create Page' }}
        </button>
      </div>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styleUrls: ['../../shared/styles/ui-controls.scss', '../../shared/styles/ui-cards.scss'],
    styles: [`
    .list-grid { padding-top: 0; }
    .page-avatar {
      display: block; width: 56px; height: 56px; margin: -40px 0 var(--space-2); object-fit: cover;
      background: var(--surface); border: 3px solid var(--surface); border-radius: var(--radius-lg);
    }
    .page-name { display: flex; align-items: center; gap: var(--space-1); }
    .page-desc {
      display: -webkit-box; margin: var(--space-1) 0 0; overflow: hidden; font-size: 13px; color: var(--text-secondary);
      -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    }
  `]
})
export class PagesComponent implements OnInit {
  pages: Page[] = [];
  loading = false;
  loadError = false;

  isCreating = false;
  saving = false;
  createForm!: FormGroup;

  constructor(
    private apiService: ApiService,
    private fb: FormBuilder,
    private snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.loadPages();
  }

  loadPages(): void {
    this.loading = true;
    this.loadError = false;
    this.apiService.getPages().subscribe({
      next: (res) => {
        this.pages = res.results;
        this.loading = false;
      },
      error: () => {
        this.loading = false;
        this.loadError = true;
      },
    });
  }

  follow(page: Page): void {
    this.apiService.followPage(page.id).subscribe(() => {
      page.is_following = true;
      page.followers_count++;
    });
  }

  unfollow(page: Page): void {
    this.apiService.unfollowPage(page.id).subscribe(() => {
      page.is_following = false;
      page.followers_count--;
    });
  }

  openCreateDialog(): void {
    this.createForm = this.fb.group({
      name: ['', Validators.required],
      category: [''],
      description: [''],
    });
    this.isCreating = true;
  }

  saveCreate(): void {
    if (this.createForm.invalid || this.saving) return;
    this.saving = true;
    this.apiService.createPage(this.createForm.value).subscribe({
      next: () => {
        this.isCreating = false;
        this.saving = false;
        this.snackBar.open('Page created!', 'Dismiss', { duration: 3000 });
        this.loadPages();
      },
      error: () => {
        this.saving = false;
        this.snackBar.open('Failed to create page', 'Dismiss', { duration: 3000 });
      },
    });
  }

  cancelCreate(): void {
    this.isCreating = false;
  }
}
