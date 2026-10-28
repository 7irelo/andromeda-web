import { ChangeDetectionStrategy, Component, inject, input } from '@angular/core';
import { NgOptimizedImage } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatDividerModule } from '@angular/material/divider';
import { AuthService } from '../../../core/services/auth.service';
import { PwaService } from '../../../core/services/pwa.service';
import { ThemeService } from '../../../core/services/theme.service';
import { User } from '../../../models/user.model';

/**
 * The avatar button and its menu. Rendered by the navbar inside `@defer (on idle)` so that
 * MatMenu and the CDK overlay are not part of the initial bundle.
 */
@Component({
  selector: 'app-profile-menu',
  imports: [NgOptimizedImage, RouterLink, MatIconModule, MatMenuModule, MatDividerModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <button type="button" class="avatar-btn" [matMenuTriggerFor]="profileMenu"
            aria-label="Account menu" i18n-aria-label="@@nav.accountMenu">
      <img [ngSrc]="user()?.avatar_url || 'assets/default-avatar.png'" alt="" class="avatar sm" width="32" height="32" />
    </button>

    <mat-menu #profileMenu="matMenu">
      <a mat-menu-item [routerLink]="'/profile/' + (user()?.username ?? '')">
        <mat-icon aria-hidden="true">person</mat-icon>
        <span i18n="@@nav.myProfile">My Profile</span>
      </a>
      <a mat-menu-item routerLink="/settings">
        <mat-icon aria-hidden="true">settings</mat-icon>
        <span i18n="@@nav.settings">Settings</span>
      </a>
      @if (user()?.is_staff) {
        <a mat-menu-item routerLink="/moderation">
          <mat-icon aria-hidden="true">gavel</mat-icon>
          <span i18n="@@nav.moderation">Moderation</span>
        </a>
      }
      <a mat-menu-item routerLink="/marketplace/mine">
        <mat-icon aria-hidden="true">storefront</mat-icon>
        <span i18n="@@nav.myListings">My Listings</span>
      </a>
      <a mat-menu-item routerLink="/saved">
        <mat-icon aria-hidden="true">bookmark</mat-icon>
        <span i18n="@@nav.saved">Saved</span>
      </a>
      <button mat-menu-item type="button" (click)="theme.toggle()">
        <mat-icon aria-hidden="true">{{ theme.isDark() ? 'light_mode' : 'dark_mode' }}</mat-icon>
        @if (theme.isDark()) {
          <span i18n="@@nav.lightTheme">Light theme</span>
        } @else {
          <span i18n="@@nav.darkTheme">Dark theme</span>
        }
      </button>
      @if (pwa.canInstall()) {
        <button mat-menu-item type="button" (click)="pwa.install()">
          <mat-icon aria-hidden="true">install_mobile</mat-icon>
          <span i18n="@@nav.installApp">Install app</span>
        </button>
      }
      <mat-divider></mat-divider>
      <button mat-menu-item type="button" (click)="auth.logout()">
        <mat-icon aria-hidden="true">logout</mat-icon>
        <span i18n="@@nav.logout">Log Out</span>
      </button>
    </mat-menu>
  `,
  styleUrl: './avatar-button.scss',
})
export class ProfileMenuComponent {
  readonly user = input<User | null>(null);
  protected readonly auth = inject(AuthService);
  protected readonly pwa = inject(PwaService);
  protected readonly theme = inject(ThemeService);
}
