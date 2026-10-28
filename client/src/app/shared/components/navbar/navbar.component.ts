import { Component, OnInit, OnDestroy, ChangeDetectionStrategy, HostListener } from '@angular/core';
import { RouterLink, RouterLinkActive, Router } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { Subscription } from 'rxjs';
import { AuthService } from '../../../core/services/auth.service';
import { WebSocketService } from '../../../core/services/websocket.service';
import { ApiService } from '../../../core/services/api.service';
import { User } from '../../../models/user.model';
import { ProfileMenuComponent } from './profile-menu.component';

/**
 * Kept deliberately light: it is in the initial bundle. No Material form-field, tooltip,
 * badge, button or FormsModule here (together they were ~250 kB); the account menu is deferred.
 */
@Component({
    selector: 'app-navbar',
    imports: [RouterLink, RouterLinkActive, MatIconModule, ProfileMenuComponent],
    templateUrl: './navbar.component.html',
    changeDetection: ChangeDetectionStrategy.Eager,
    styleUrls: ['./navbar.component.scss']
})
export class NavbarComponent implements OnInit, OnDestroy {
  currentUser: User | null = null;
  unreadNotifications = 0;
  unreadChats = 0;
  mobileMenuOpen = false;
  /** Read out by the polite live region when a notification arrives over the socket. */
  announcement = '';

  readonly navItems = [
    { icon: 'home', label: $localize`:@@nav.feed:Feed`, route: '/feed' },
    { icon: 'people', label: $localize`:@@nav.friends:Friends`, route: '/friends' },
    { icon: 'group', label: $localize`:@@nav.groups:Groups`, route: '/groups' },
    { icon: 'play_circle', label: $localize`:@@nav.watch:Watch`, route: '/watch' },
    { icon: 'storefront', label: $localize`:@@nav.marketplace:Marketplace`, route: '/marketplace' },
    { icon: 'auto_stories', label: $localize`:@@nav.pages:Pages`, route: '/pages' },
  ];
  readonly messengerLabel = $localize`:@@nav.messenger:Messenger`;
  readonly notificationsLabel = $localize`:@@nav.notifications:Notifications`;
  readonly chatsLabel = $localize`:@@nav.chats:Chats`;
  readonly alertsLabel = $localize`:@@nav.alerts:Alerts`;
  readonly openMenuLabel = $localize`:@@nav.openMenu:Open menu`;
  readonly closeMenuLabel = $localize`:@@nav.closeMenu:Close menu`;

  private subs = new Subscription();

  constructor(
    public authService: AuthService,
    private wsService: WebSocketService,
    private apiService: ApiService,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.subs.add(this.authService.currentUser$.subscribe((u) => (this.currentUser = u)));
    this.subs.add(this.wsService.unreadCount$.subscribe((n) => (this.unreadNotifications = n)));
    this.subs.add(this.wsService.chatUnread$.subscribe((n) => (this.unreadChats = n)));
    this.subs.add(this.wsService.notification$.subscribe((n) => {
      // Same filter as the notifications page: other socket events aren't notifications.
      if (!n || typeof n.id !== 'number' || String(n.type ?? '').includes('.')) return;
      this.announcement = '';
      // Re-set on the next tick so repeated identical titles are still announced.
      setTimeout(() => (this.announcement = $localize`:@@nav.newNotification:New notification: ${n.title}:title:`), 50);
    }));
    this.wsService.refreshChatUnread();
    this.apiService.getUnreadCount().subscribe({
      next: ({ unread_count }) => this.wsService.unreadCount$.next(unread_count),
      error: () => {},
    });
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
  }

  badge(n: number): string {
    return n > 99 ? '99+' : String(n);
  }

  chatAriaLabel(): string {
    return this.unreadChats
      ? $localize`:@@nav.messengerUnread:Messenger, ${this.unreadChats}:count: unread conversations`
      : this.messengerLabel;
  }

  notificationsAriaLabel(): string {
    return this.unreadNotifications
      ? $localize`:@@nav.notificationsUnread:Notifications, ${this.unreadNotifications}:count: unread`
      : this.notificationsLabel;
  }

  search(event: Event, input: HTMLInputElement): void {
    event.preventDefault();
    const q = input.value.trim();
    if (!q) return;
    this.router.navigate(['/search'], { queryParams: { q } });
    this.mobileMenuOpen = false;
    input.blur();
  }

  toggleMobileMenu(): void {
    this.mobileMenuOpen = !this.mobileMenuOpen;
  }

  @HostListener('document:keydown.escape')
  closeMobileMenu(): void {
    this.mobileMenuOpen = false;
  }
}
