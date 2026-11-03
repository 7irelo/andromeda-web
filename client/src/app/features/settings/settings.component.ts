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
    <div class="settings-page ui-controls">
      <div class="page-head">
        <div>
          <h1 i18n="@@nav.settings">Settings</h1>
          <p i18n="@@settings.subtitle">Manage your account preferences</p>
        </div>
      </div>

      <div class="settings-layout">
      <nav class="settings-nav" aria-label="Settings sections" i18n-aria-label="@@settings.sectionsLabel">
        <button *ngFor="let item of sections" type="button" class="nav-link" [class.active]="activeSection === item.id"
                [attr.aria-current]="activeSection === item.id ? 'true' : null" (click)="activeSection = item.id">
          <mat-icon aria-hidden="true">{{ item.icon }}</mat-icon>
          <span>{{ item.label }}</span>
        </button>
      </nav>

      <div class="settings-panels">

      <!-- Profile Section -->
      <section class="settings-section card" [hidden]="activeSection !== 'profile'">
        <h2 i18n="@@settings.editProfile">Edit Profile</h2>
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
      <section class="settings-section card" [hidden]="activeSection !== 'privacy'">
        <h2 i18n="@@settings.privacy">Privacy Settings</h2>
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
            <mat-slide-toggle color="primary" formControlName="show_online_status" aria-labelledby="online-label" aria-describedby="online-hint"></mat-slide-toggle>
          </div>

          <div class="setting-item">
            <div>
              <div class="font-semibold" id="search-label" i18n="@@settings.searchable">Appear in Search Results</div>
              <div class="text-secondary text-sm" id="search-hint" i18n="@@settings.searchableHint">Allow others to find you via search</div>
            </div>
            <mat-slide-toggle color="primary" formControlName="searchable" aria-labelledby="search-label" aria-describedby="search-hint"></mat-slide-toggle>
          </div>

          <button mat-flat-button color="primary" type="submit" [disabled]="savingPrivacy">
            <mat-spinner diameter="18" *ngIf="savingPrivacy"></mat-spinner>
            <span *ngIf="!savingPrivacy" i18n="@@settings.savePrivacy">Save Privacy Settings</span>
          </button>
        </form>
      </section>

      <!-- Appearance -->
      <section class="settings-section card" [hidden]="activeSection !== 'appearance'">
        <h2 i18n="@@settings.appearance">Appearance</h2>
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
      <section class="settings-section card" [hidden]="activeSection !== 'password'">
        <h2 i18n="@@settings.changePassword">Change Password</h2>
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
        <div class="setting-item separated">
          <div>
            <div class="font-semibold" i18n="@@settings.signOutEverywhere">Sign out everywhere</div>
            <div class="text-secondary text-sm" i18n="@@settings.signOutEverywhereHint">End every session on every device, including this one</div>
          </div>
          <button mat-stroked-button (click)="logoutEverywhere()" i18n="@@settings.signOutAll">Sign out all devices</button>
        </div>
      </section>

      <div [hidden]="activeSection !== 'notifications'"><app-notification-settings></app-notification-settings></div>

      <div [hidden]="activeSection !== 'security'"><app-security-settings></app-security-settings></div>

      <div [hidden]="activeSection !== 'data'"><app-data-settings></app-data-settings></div>

      <div [hidden]="activeSection !== 'tokens'"><app-token-settings></app-token-settings></div>

      <!-- Danger Zone -->
      <section class="settings-section card danger-zone" [hidden]="activeSection !== 'danger'">
        <h2 i18n="@@settings.dangerZone">Danger Zone</h2>
        <div class="setting-item">
          <div>
            <div class="font-semibold" i18n="@@settings.deleteAccount">Delete Account</div>
            <div class="text-secondary text-sm" i18n="@@settings.deleteHint">You're signed out now and everything is permanently deleted after
              14 days. Sign in before then to cancel.</div>
          </div>
          <button mat-stroked-button class="btn-danger" *ngIf="!showDelete" (click)="showDelete = true" i18n="@@settings.deleteAccount">Delete Account</button>
        </div>
        <div *ngIf="showDelete" class="settings-form separated">
          <mat-form-field appearance="outline" class="w-full">
            <mat-label i18n="@@settings.confirmWithPassword">Enter your password to confirm</mat-label>
            <input matInput type="password" autocomplete="current-password" [(ngModel)]="deletePassword" />
          </mat-form-field>
          <div class="confirm-actions">
            <button mat-stroked-button (click)="showDelete = false; deletePassword = ''" i18n="@@common.cancel">Cancel</button>
            <button mat-stroked-button class="btn-danger" [disabled]="!deletePassword || deleting" (click)="confirmDelete()">
              @if (deleting) { <span i18n="@@settings.deleting">Deleting...</span> } @else { <span i18n="@@settings.deleteForever">Permanently delete my account</span> }
            </button>
          </div>
        </div>
      </section>
      </div>
      </div>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styleUrls: ['../../shared/styles/ui-controls.scss', './settings-section.scss'],
    styles: [`
    .settings-page { max-width: 1000px; margin: 0 auto; padding: var(--space-6); }
    .settings-layout { display: grid; grid-template-columns: 200px minmax(0, 1fr); align-items: start; gap: var(--space-6); }
    .settings-nav {
      position: sticky; top: calc(var(--header-height) + var(--space-4));
      display: flex; flex-direction: column; gap: 2px;
    }
    .nav-link {
      display: flex; align-items: center; gap: 10px; width: 100%; min-height: 36px; padding: 0 var(--space-3);
      background: none; border: 0; border-radius: var(--radius-sm); color: var(--text-secondary);
      font: inherit; font-size: 13px; font-weight: 500; text-align: left; white-space: nowrap; cursor: pointer;
    }
    .nav-link:hover { background: var(--surface-2); color: var(--text-primary); }
    .nav-link.active { background: var(--primary-light); color: var(--primary); }
    .nav-link mat-icon { flex: none; width: 18px; height: 18px; font-size: 18px; }
    .settings-form { display: flex; flex-direction: column; }
    .settings-form > button { align-self: flex-start; }
    .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3); }
    .setting-item {
      display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap;
      gap: var(--space-2) var(--space-4); padding: var(--space-3) 0;
    }
    .setting-item > div:first-child { flex: 1 1 200px; min-width: 0; }
    .separated { margin-top: var(--space-4); padding-top: var(--space-4); border-top: 1px solid var(--border); }
    .confirm-actions { display: flex; flex-wrap: wrap; gap: var(--space-2); }
    .danger-zone h2 { color: var(--danger-text); }
    mat-button-toggle-group {
      --mat-button-toggle-shape: var(--radius-sm);
      --mat-button-toggle-height: 36px;
      --mat-button-toggle-label-text-size: 13px;
      --mat-button-toggle-selected-state-background-color: var(--primary-light);
      --mat-button-toggle-selected-state-text-color: var(--primary);
      --mat-button-toggle-divider-color: var(--border-strong);
    }
    @media (max-width: 760px) {
      .settings-layout { grid-template-columns: minmax(0, 1fr); gap: var(--space-4); }
      .settings-nav {
        position: static; flex-direction: row; flex-wrap: wrap; gap: var(--space-1);
      }
      .nav-link { width: auto; flex: none; min-height: var(--touch-target); }
      .nav-link mat-icon { display: none; }
    }
    @media (max-width: 600px) {
      .settings-page { padding: var(--space-4); }
      .form-row { grid-template-columns: minmax(0, 1fr); gap: 0; }
      mat-button-toggle-group { --mat-button-toggle-height: var(--touch-target); }
    }
  `]
})
export class SettingsComponent implements OnInit {
  readonly sections = [
    { id: 'profile', icon: 'person', label: $localize`:@@settings.nav.profile:Profile` },
    { id: 'privacy', icon: 'shield', label: $localize`:@@settings.nav.privacy:Privacy` },
    { id: 'appearance', icon: 'palette', label: $localize`:@@settings.appearance:Appearance` },
    { id: 'password', icon: 'lock', label: $localize`:@@settings.nav.password:Password` },
    { id: 'notifications', icon: 'notifications', label: $localize`:@@settings.nav.notifications:Notifications` },
    { id: 'security', icon: 'verified_user', label: $localize`:@@settings.nav.security:Security` },
    { id: 'data', icon: 'folder_zip', label: $localize`:@@settings.nav.data:Your data` },
    { id: 'tokens', icon: 'key', label: $localize`:@@settings.nav.tokens:Access tokens` },
    { id: 'danger', icon: 'warning', label: $localize`:@@settings.dangerZone:Danger Zone` },
  ];
  activeSection = 'profile';

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
