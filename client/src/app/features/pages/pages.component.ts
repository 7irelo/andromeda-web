import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../core/services/api.service';
import { Page } from '../../models/page.model';

@Component({
  selector: 'app-pages',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule,
    MatIconModule, MatButtonModule, MatProgressSpinnerModule,
    MatFormFieldModule, MatInputModule, MatSnackBarModule,
  ],
  template: `
    <div class="pages-page">
      <div class="page-header-gradient">
        <div>
          <h1>Pages</h1>
          <p style="opacity:.8;margin-top:4px;font-size:14px">Discover and follow community pages</p>
        </div>
        <button mat-flat-button (click)="openCreateDialog()" style="background:#fff;color:var(--primary);font-weight:600">
          <mat-icon>add</mat-icon> Create Page
        </button>
      </div>

      <div *ngIf="loading" class="loading-center"><mat-spinner diameter="40"></mat-spinner></div>

      <div class="pages-grid" *ngIf="!loading">
        <div class="page-card card" *ngFor="let p of pages">
          <div class="page-cover">
            <img [src]="p.cover_photo || 'assets/default-cover.png'" alt="" />
          </div>
          <div class="page-body">
            <img [src]="p.avatar || 'assets/default-avatar.png'" class="page-avatar" [alt]="p.name" />
            <div class="page-info">
              <div class="font-semibold">{{ p.name }}</div>
              <div class="text-secondary text-sm">{{ p.category || 'Community' }} · {{ p.followers_count | number }} followers</div>
              <p class="page-desc text-sm" *ngIf="p.description">{{ p.description }}</p>
            </div>
            <div class="page-actions">
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

      <div *ngIf="!loading && pages.length === 0" class="empty-state">
        <mat-icon>auto_stories</mat-icon>
        <p>No pages yet. Create the first one!</p>
      </div>
    </div>

    <!-- Create Dialog -->
    <div class="edit-overlay" *ngIf="isCreating" (click)="cancelCreate()"></div>
    <div class="edit-dialog card" *ngIf="isCreating" [formGroup]="createForm">
      <div class="edit-dialog-header">
        <h2>Create Page</h2>
        <button mat-icon-button (click)="cancelCreate()"><mat-icon>close</mat-icon></button>
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
  styles: [`
    .pages-page { max-width: 1100px; margin: 0 auto; padding: 16px; }
    .page-header-gradient {
      display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px;
    }
    .page-header-gradient h1 { font-size: 24px; font-weight: 800; color: #fff; }
    .pages-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
    .page-card { overflow: hidden; transition: transform .2s, box-shadow .2s; }
    .page-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-md); }
    .page-cover { height: 100px; overflow: hidden; background: var(--gradient-accent); }
    .page-cover img { width: 100%; height: 100%; object-fit: cover; }
    .page-body { padding: 16px; display: flex; flex-direction: column; gap: 10px; position: relative; }
    .page-avatar {
      width: 56px; height: 56px; border-radius: 12px; object-fit: cover;
      border: 3px solid var(--surface); margin-top: -40px; box-shadow: var(--shadow);
    }
    .page-info { display: flex; flex-direction: column; gap: 2px; }
    .page-desc { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; color: var(--text-secondary); }
    .page-actions { margin-top: 4px; }
    .loading-center { display: flex; justify-content: center; padding: 40px; }
    .empty-state {
      display: flex; flex-direction: column; align-items: center; padding: 60px; color: var(--text-secondary); gap: 12px;
    }
    .empty-state mat-icon { font-size: 48px; width: 48px; height: 48px; opacity: .4; }

    .edit-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.45); z-index: 100; backdrop-filter: blur(2px); }
    .edit-dialog {
      position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
      z-index: 101; width: min(480px, 95vw); max-height: 90vh; overflow-y: auto; padding: 0;
    }
    .edit-dialog-header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 20px 24px 16px; border-bottom: 1px solid var(--border);
      position: sticky; top: 0; background: var(--surface); z-index: 1;
    }
    .edit-dialog-header h2 { font-size: 18px; font-weight: 700; margin: 0; }
    .edit-dialog-body { padding: 20px 24px; display: flex; flex-direction: column; gap: 8px; }
    .edit-dialog-actions {
      display: flex; justify-content: flex-end; gap: 10px; padding: 16px 24px;
      border-top: 1px solid var(--border); position: sticky; bottom: 0; background: var(--surface);
    }
    .w-full { width: 100%; }
  `]
})
export class PagesComponent implements OnInit {
  pages: Page[] = [];
  loading = false;

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
    this.apiService.getPages().subscribe({
      next: (res) => {
        this.pages = res.results;
        this.loading = false;
      },
      error: () => (this.loading = false),
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
