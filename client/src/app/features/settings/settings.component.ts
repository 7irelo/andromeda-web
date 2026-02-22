import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { AuthService } from '../../core/services/auth.service';
import { ApiService } from '../../core/services/api.service';
import { User } from '../../models/user.model';

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule,
    MatIconModule, MatButtonModule, MatFormFieldModule, MatInputModule,
    MatSlideToggleModule, MatSnackBarModule, MatProgressSpinnerModule,
  ],
  template: `
    <div class="settings-page">
      <div class="page-header-gradient">
        <h1><mat-icon>settings</mat-icon> Settings</h1>
        <p>Manage your account preferences</p>
      </div>

      <!-- Profile Section -->
      <section class="settings-section card">
        <h2><mat-icon>person</mat-icon> Edit Profile</h2>
        <form [formGroup]="profileForm" (ngSubmit)="saveProfile()" class="settings-form">
          <div class="form-row">
            <mat-form-field appearance="outline">
              <mat-label>First Name</mat-label>
              <input matInput formControlName="first_name" />
            </mat-form-field>
            <mat-form-field appearance="outline">
              <mat-label>Last Name</mat-label>
              <input matInput formControlName="last_name" />
            </mat-form-field>
          </div>
          <mat-form-field appearance="outline" class="w-full">
            <mat-label>Bio</mat-label>
            <textarea matInput formControlName="bio" rows="3"></textarea>
          </mat-form-field>
          <mat-form-field appearance="outline" class="w-full">
            <mat-label>Location</mat-label>
            <input matInput formControlName="location" />
          </mat-form-field>
          <mat-form-field appearance="outline" class="w-full">
            <mat-label>Website</mat-label>
            <input matInput formControlName="website" />
          </mat-form-field>
          <button mat-flat-button color="primary" type="submit" [disabled]="savingProfile">
            <mat-spinner diameter="18" *ngIf="savingProfile"></mat-spinner>
            <span *ngIf="!savingProfile">Save Changes</span>
          </button>
        </form>
      </section>

      <!-- Appearance -->
      <section class="settings-section card">
        <h2><mat-icon>palette</mat-icon> Appearance</h2>
        <div class="setting-item">
          <div>
            <div class="font-semibold">Dark Mode</div>
            <div class="text-secondary text-sm">Switch between light and dark themes</div>
          </div>
          <mat-slide-toggle [checked]="isDark" (change)="toggleTheme($event.checked)"></mat-slide-toggle>
        </div>
      </section>

      <!-- Password -->
      <section class="settings-section card">
        <h2><mat-icon>lock</mat-icon> Change Password</h2>
        <form [formGroup]="passwordForm" (ngSubmit)="changePassword()" class="settings-form">
          <mat-form-field appearance="outline" class="w-full">
            <mat-label>Current Password</mat-label>
            <input matInput type="password" formControlName="current_password" />
          </mat-form-field>
          <mat-form-field appearance="outline" class="w-full">
            <mat-label>New Password</mat-label>
            <input matInput type="password" formControlName="new_password" />
          </mat-form-field>
          <button mat-flat-button color="primary" type="submit" [disabled]="passwordForm.invalid">
            Update Password
          </button>
        </form>
      </section>

      <!-- Danger Zone -->
      <section class="settings-section card danger-zone">
        <h2><mat-icon>warning</mat-icon> Danger Zone</h2>
        <div class="setting-item">
          <div>
            <div class="font-semibold">Delete Account</div>
            <div class="text-secondary text-sm">Permanently delete your account and all data</div>
          </div>
          <button mat-stroked-button color="warn" (click)="confirmDelete()">Delete Account</button>
        </div>
      </section>
    </div>
  `,
  styles: [`
    .settings-page { max-width: 700px; margin: 0 auto; padding: 16px; }
    .page-header-gradient {
      background: var(--gradient-primary); color: #fff; padding: 28px 32px;
      border-radius: var(--border-radius); margin-bottom: 20px;
    }
    .page-header-gradient h1 { font-size: 24px; font-weight: 800; display: flex; align-items: center; gap: 10px; }
    .page-header-gradient p { opacity: .85; margin-top: 4px; font-size: 14px; }
    .settings-section { padding: 24px; margin-bottom: 16px; }
    .settings-section h2 {
      font-size: 18px; font-weight: 700; margin-bottom: 16px;
      display: flex; align-items: center; gap: 8px;
    }
    .settings-form { display: flex; flex-direction: column; gap: 8px; }
    .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    @media (max-width: 500px) { .form-row { grid-template-columns: 1fr; } }
    .setting-item {
      display: flex; align-items: center; justify-content: space-between; gap: 16px;
      padding: 12px 0;
    }
    .danger-zone { border-color: var(--danger); }
    .danger-zone h2 { color: var(--danger); }
  `]
})
export class SettingsComponent implements OnInit {
  currentUser: User | null = null;
  isDark = false;
  savingProfile = false;

  profileForm = this.fb.group({
    first_name: [''],
    last_name: [''],
    bio: [''],
    location: [''],
    website: [''],
  });

  passwordForm = this.fb.group({
    current_password: ['', Validators.required],
    new_password: ['', [Validators.required, Validators.minLength(8)]],
  });

  constructor(
    private fb: FormBuilder,
    private authService: AuthService,
    private apiService: ApiService,
    private snackBar: MatSnackBar,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.isDark = localStorage.getItem('theme') === 'dark';
    this.authService.currentUser$.subscribe((u) => {
      this.currentUser = u;
      if (u) {
        this.profileForm.patchValue({
          first_name: u.first_name,
          last_name: u.last_name,
          bio: u.bio,
          location: u.location,
          website: u.website,
        });
      }
    });
  }

  saveProfile(): void {
    if (this.savingProfile) return;
    this.savingProfile = true;
    this.apiService.updateProfile(this.profileForm.value as Partial<User>).subscribe({
      next: () => {
        this.savingProfile = false;
        this.authService.fetchMe().subscribe();
        this.snackBar.open('Profile updated!', 'Dismiss', { duration: 3000 });
      },
      error: () => {
        this.savingProfile = false;
        this.snackBar.open('Failed to update profile', 'Dismiss', { duration: 3000 });
      },
    });
  }

  toggleTheme(dark: boolean): void {
    this.isDark = dark;
    const theme = dark ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }

  changePassword(): void {
    this.snackBar.open('Password change coming soon', 'Dismiss', { duration: 3000 });
  }

  confirmDelete(): void {
    if (confirm('Are you sure you want to delete your account? This cannot be undone.')) {
      const refresh = localStorage.getItem('refresh_token') || '';
      this.apiService.deleteAccount(refresh).subscribe({
        next: () => {
          this.authService.logout();
          this.router.navigate(['/login']);
        },
        error: () => this.snackBar.open('Failed to delete account', 'Dismiss', { duration: 3000 }),
      });
    }
  }
}
