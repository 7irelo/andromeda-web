import { Component, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { AuthService } from '../../core/services/auth.service';
import { ApiService } from '../../core/services/api.service';
import { User } from '../../models/user.model';
import { ThemePreference, ThemeService } from '../../core/services/theme.service';
import { SecuritySettingsComponent } from './security-settings.component';
import { NotificationSettingsComponent } from './notification-settings.component';
import { DataSettingsComponent } from './data-settings.component';
import { TokenSettingsComponent } from './token-settings.component';

@Component({
    selector: 'app-settings',
    imports: [
        CommonModule, FormsModule, ReactiveFormsModule,
        MatIconModule, MatButtonModule, MatFormFieldModule, MatInputModule,
        MatSelectModule, MatSlideToggleModule, MatButtonToggleModule, MatSnackBarModule, MatProgressSpinnerModule,
        SecuritySettingsComponent, NotificationSettingsComponent, DataSettingsComponent, TokenSettingsComponent,
    ],
    template: `
    <div class="settings-page">
      <div class="page-header-gradient">
        <h1><mat-icon aria-hidden="true">settings</mat-icon> <span i18n="@@nav.settings">Settings</span></h1>
        <p i18n="@@settings.subtitle">Manage your account preferences</p>
      </div>

      <!-- Profile Section -->
      <section class="settings-section card">
        <h2><mat-icon aria-hidden="true">person</mat-icon> <span i18n="@@settings.editProfile">Edit Profile</span></h2>
        <form [formGroup]="profileForm" (ngSubmit)="saveProfile()" class="settings-form">
          <div class="form-row">
            <mat-form-field appearance="outline">
              <mat-label i18n="@@register.firstName">First Name</mat-label>
              <input matInput formControlName="first_name" autocomplete="given-name" />
            </mat-form-field>
            <mat-form-field appearance="outline">
              <mat-label i18n="@@register.lastName">Last Name</mat-label>
              <input matInput formControlName="last_name" autocomplete="family-name" />
            </mat-form-field>
          </div>
          <mat-form-field appearance="outline" class="w-full">
            <mat-label i18n="@@register.bio">Bio</mat-label>
            <textarea matInput formControlName="bio" rows="3"></textarea>
          </mat-form-field>
          <mat-form-field appearance="outline" class="w-full">
            <mat-label i18n="@@register.location">Location</mat-label>
            <input matInput formControlName="location" />
          </mat-form-field>
          <mat-form-field appearance="outline" class="w-full">
            <mat-label i18n="@@settings.website">Website</mat-label>
            <input matInput type="url" formControlName="website" autocomplete="url" />
          </mat-form-field>
          <button mat-flat-button color="primary" type="submit" [disabled]="savingProfile">
            <mat-spinner diameter="18" *ngIf="savingProfile"></mat-spinner>
            <span *ngIf="!savingProfile" i18n="@@settings.save">Save Changes</span>
          </button>
        </form>
      </section>

      <!-- Privacy Section -->
      <section class="settings-section card">
        <h2><mat-icon aria-hidden="true">shield</mat-icon> <span i18n="@@settings.privacy">Privacy Settings</span></h2>
        <form [formGroup]="privacyForm" (ngSubmit)="savePrivacy()" class="settings-form">
          <mat-form-field appearance="outline" class="w-full">
            <mat-label i18n="@@settings.profileVisibility">Profile Visibility</mat-label>
            <mat-select formControlName="privacy_profile">
              <mat-option value="everyone" i18n="@@settings.everyone">Everyone</mat-option>
              <mat-option value="friends" i18n="@@settings.friends">Friends</mat-option>
              <mat-option value="private" i18n="@@settings.onlyMe">Only Me</mat-option>
            </mat-select>
          </mat-form-field>

          <mat-form-field appearance="outline" class="w-full">
            <mat-label i18n="@@settings.whoCanMessage">Who Can Message Me</mat-label>
            <mat-select formControlName="privacy_messages">
              <mat-option value="everyone" i18n="@@settings.everyone">Everyone</mat-option>
              <mat-option value="friends" i18n="@@settings.friends">Friends</mat-option>
              <mat-option value="nobody" i18n="@@settings.nobody">Nobody</mat-option>
            </mat-select>
          </mat-form-field>

          <mat-form-field appearance="outline" class="w-full">
            <mat-label i18n="@@settings.whoCanRequest">Who Can Send Friend Requests</mat-label>
            <mat-select formControlName="privacy_friend_requests">
              <mat-option value="everyone" i18n="@@settings.everyone">Everyone</mat-option>
              <mat-option value="friends_of_friends" i18n="@@settings.friendsOfFriends">Friends of Friends</mat-option>
              <mat-option value="nobody" i18n="@@settings.nobody">Nobody</mat-option>
            </mat-select>
          </mat-form-field>

          <mat-form-field appearance="outline" class="w-full">
            <mat-label i18n="@@settings.friendsListVisibility">Friends List Visibility</mat-label>
            <mat-select formControlName="privacy_friends_list">
              <mat-option value="everyone" i18n="@@settings.everyone">Everyone</mat-option>
              <mat-option value="friends" i18n="@@settings.friends">Friends</mat-option>
              <mat-option value="private" i18n="@@settings.onlyMe">Only Me</mat-option>
            </mat-select>
          </mat-form-field>

          <mat-form-field appearance="outline" class="w-full">
            <mat-label i18n="@@settings.defaultPostPrivacy">Default Post Privacy</mat-label>
            <mat-select formControlName="default_post_privacy">
              <mat-option value="public" i18n="@@settings.public">Public</mat-option>
              <mat-option value="friends" i18n="@@settings.friends">Friends</mat-option>
              <mat-option value="private" i18n="@@settings.onlyMe">Only Me</mat-option>
            </mat-select>
          </mat-form-field>

          <div class="setting-item">
            <div>
              <div class="font-semibold" id="online-label" i18n="@@settings.onlineStatus">Show Online Status</div>
              <div class="text-secondary text-sm" id="online-hint" i18n="@@settings.onlineStatusHint">Let others see when you're active</div>
            </div>
            <mat-slide-toggle formControlName="show_online_status" aria-labelledby="online-label" aria-describedby="online-hint"></mat-slide-toggle>
          </div>

          <div class="setting-item">
            <div>
              <div class="font-semibold" id="search-label" i18n="@@settings.searchable">Appear in Search Results</div>
              <div class="text-secondary text-sm" id="search-hint" i18n="@@settings.searchableHint">Allow others to find you via search</div>
            </div>
            <mat-slide-toggle formControlName="searchable" aria-labelledby="search-label" aria-describedby="search-hint"></mat-slide-toggle>
          </div>

          <button mat-flat-button color="primary" type="submit" [disabled]="savingPrivacy">
            <mat-spinner diameter="18" *ngIf="savingPrivacy"></mat-spinner>
            <span *ngIf="!savingPrivacy" i18n="@@settings.savePrivacy">Save Privacy Settings</span>
          </button>
        </form>
      </section>

      <!-- Appearance -->
      <section class="settings-section card">
        <h2><mat-icon aria-hidden="true">palette</mat-icon> <span i18n="@@settings.appearance">Appearance</span></h2>
        <div class="setting-item">
          <div>
            <div class="font-semibold" id="theme-label" i18n="@@settings.theme">Theme</div>
            <div class="text-secondary text-sm" i18n="@@settings.themeHint">Match your device, or always use light or dark</div>
          </div>
          <mat-button-toggle-group [value]="theme.preference()" (change)="setTheme($event.value)"
                                   aria-labelledby="theme-label" hideSingleSelectionIndicator>
            <mat-button-toggle value="system" i18n="@@settings.themeSystem">System</mat-button-toggle>
            <mat-button-toggle value="light" i18n="@@settings.themeLight">Light</mat-button-toggle>
            <mat-button-toggle value="dark" i18n="@@settings.themeDark">Dark</mat-button-toggle>
          </mat-button-toggle-group>
        </div>
      </section>

      <!-- Password -->
      <section class="settings-section card">
        <h2><mat-icon aria-hidden="true">lock</mat-icon> <span i18n="@@settings.changePassword">Change Password</span></h2>
        <form [formGroup]="passwordForm" (ngSubmit)="changePassword()" class="settings-form">
          <mat-form-field appearance="outline" class="w-full">
            <mat-label i18n="@@settings.currentPassword">Current Password</mat-label>
            <input matInput type="password" formControlName="current_password" autocomplete="current-password" />
          </mat-form-field>
          <mat-form-field appearance="outline" class="w-full">
            <mat-label i18n="@@reset.newPassword">New password</mat-label>
            <input matInput type="password" formControlName="new_password" autocomplete="new-password" />
          </mat-form-field>
          <button mat-flat-button color="primary" type="submit" [disabled]="passwordForm.invalid || changingPassword">
            @if (changingPassword) { <span i18n="@@settings.updating">Updating...</span> } @else { <span i18n="@@reset.update">Update password</span> }
          </button>
        </form>
        <div class="setting-item" style="margin-top:16px">
          <div>
            <div class="font-semibold" i18n="@@settings.signOutEverywhere">Sign out everywhere</div>
            <div class="text-secondary text-sm" i18n="@@settings.signOutEverywhereHint">End every session on every device, including this one</div>
          </div>
          <button mat-stroked-button (click)="logoutEverywhere()" i18n="@@settings.signOutAll">Sign out all devices</button>
        </div>
      </section>

      <app-notification-settings></app-notification-settings>

      <app-security-settings></app-security-settings>

      <app-data-settings></app-data-settings>

      <app-token-settings></app-token-settings>

      <!-- Danger Zone -->
      <section class="settings-section card danger-zone">
        <h2><mat-icon aria-hidden="true">warning</mat-icon> <span i18n="@@settings.dangerZone">Danger Zone</span></h2>
        <div class="setting-item">
          <div>
            <div class="font-semibold" i18n="@@settings.deleteAccount">Delete Account</div>
            <div class="text-secondary text-sm" i18n="@@settings.deleteHint">You're signed out now and everything is permanently deleted after
              14 days. Sign in before then to cancel.</div>
          </div>
          <button mat-stroked-button color="warn" *ngIf="!showDelete" (click)="showDelete = true" i18n="@@settings.deleteAccount">Delete Account</button>
        </div>
        <div *ngIf="showDelete" class="settings-form" style="margin-top:12px">
          <mat-form-field appearance="outline" class="w-full">
            <mat-label i18n="@@settings.confirmWithPassword">Enter your password to confirm</mat-label>
            <input matInput type="password" autocomplete="current-password" [(ngModel)]="deletePassword" />
          </mat-form-field>
          <div style="display:flex;gap:8px">
            <button mat-stroked-button (click)="showDelete = false; deletePassword = ''" i18n="@@common.cancel">Cancel</button>
            <button mat-flat-button color="warn" [disabled]="!deletePassword || deleting" (click)="confirmDelete()">
              @if (deleting) { <span i18n="@@settings.deleting">Deleting...</span> } @else { <span i18n="@@settings.deleteForever">Permanently delete my account</span> }
            </button>
          </div>
        </div>
      </section>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
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
      padding: 12px 0; flex-wrap: wrap;
    }
    .danger-zone { border-color: var(--danger); }
    .danger-zone h2 { color: var(--danger); }
  `]
})
export class SettingsComponent implements OnInit {
  currentUser: User | null = null;
  changingPassword = false;
  showDelete = false;
  deletePassword = '';
  deleting = false;
  savingProfile = false;
  savingPrivacy = false;

  profileForm = this.fb.group({
    first_name: [''],
    last_name: [''],
    bio: [''],
    location: [''],
    website: [''],
  });

  privacyForm = this.fb.group({
    privacy_profile: ['everyone'],
    privacy_messages: ['everyone'],
    privacy_friend_requests: ['everyone'],
    privacy_friends_list: ['everyone'],
    default_post_privacy: ['public'],
    show_online_status: [true],
    searchable: [true],
  });

  passwordForm = this.fb.group({
    current_password: ['', Validators.required],
    new_password: ['', [Validators.required, Validators.minLength(10)]],
  });

  constructor(
    private fb: FormBuilder,
    private authService: AuthService,
    private apiService: ApiService,
    private snackBar: MatSnackBar,
    private router: Router,
    protected theme: ThemeService,
  ) {}

  ngOnInit(): void {
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
        this.privacyForm.patchValue({
          privacy_profile: u.privacy_profile || 'everyone',
          privacy_messages: u.privacy_messages || 'everyone',
          privacy_friend_requests: u.privacy_friend_requests || 'everyone',
          privacy_friends_list: u.privacy_friends_list || 'everyone',
          default_post_privacy: u.default_post_privacy || 'public',
          show_online_status: u.show_online_status ?? true,
          searchable: u.searchable ?? true,
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
        this.snackBar.open($localize`:@@settings.profileSaved:Profile updated!`, $localize`:@@common.dismiss:Dismiss`, { duration: 3000 });
      },
      error: () => {
        this.savingProfile = false;
        this.snackBar.open($localize`:@@register.profileFailed:Failed to update profile`, $localize`:@@common.dismiss:Dismiss`, { duration: 3000 });
      },
    });
  }

  savePrivacy(): void {
    if (this.savingPrivacy) return;
    this.savingPrivacy = true;
    this.apiService.updateProfile(this.privacyForm.value as Partial<User>).subscribe({
      next: () => {
        this.savingPrivacy = false;
        this.authService.fetchMe().subscribe();
        this.snackBar.open($localize`:@@settings.privacySaved:Privacy settings saved!`, $localize`:@@common.dismiss:Dismiss`, { duration: 3000 });
      },
      error: () => {
        this.savingPrivacy = false;
        this.snackBar.open($localize`:@@settings.privacyFailed:Failed to update privacy settings`, $localize`:@@common.dismiss:Dismiss`, { duration: 3000 });
      },
    });
  }

  setTheme(pref: ThemePreference): void {
    this.theme.set(pref);
  }

  changePassword(): void {
    if (this.passwordForm.invalid || this.changingPassword) return;
    const { current_password, new_password } = this.passwordForm.value as { current_password: string; new_password: string };
    this.changingPassword = true;
    this.authService.changePassword(current_password, new_password).subscribe({
      next: () => {
        this.changingPassword = false;
        this.passwordForm.reset();
        this.snackBar.open($localize`:@@settings.passwordUpdated:Password updated. Other devices have been signed out.`, $localize`:@@common.dismiss:Dismiss`, { duration: 4000 });
      },
      error: (err) => {
        this.changingPassword = false;
        const e = err?.error ?? {};
        const msg = e.current_password?.[0] ?? e.new_password?.[0] ?? e.non_field_errors?.[0]
          ?? $localize`:@@settings.passwordFailed:Failed to update password`;
        this.snackBar.open(msg, $localize`:@@common.dismiss:Dismiss`, { duration: 4000 });
      },
    });
  }

  logoutEverywhere(): void {
    this.authService.logoutEverywhere();
  }

  confirmDelete(): void {
    if (!this.deletePassword || this.deleting) return;
    this.deleting = true;
    this.authService.deleteAccount(this.deletePassword).subscribe({
      error: (err) => {
        this.deleting = false;
        this.deletePassword = '';
        this.snackBar.open(err?.error?.password?.[0] ?? $localize`:@@settings.deleteFailed:Failed to delete account`,
          $localize`:@@common.dismiss:Dismiss`, { duration: 3000 });
      },
    });
  }
}
