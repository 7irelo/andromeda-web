import { Component, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../core/services/api.service';
import { WebSocketService } from '../../core/services/websocket.service';
import { Notification } from '../../models/notification.model';

@Component({
    selector: 'app-notifications',
    imports: [CommonModule, MatIconModule, MatButtonModule, MatProgressSpinnerModule],
    templateUrl: './notifications.component.html',
    changeDetection: ChangeDetectionStrategy.Eager,
    styleUrls: ['./notifications.component.scss']
})
export class NotificationsComponent implements OnInit {
  notifications: Notification[] = [];
  loading = false;

  constructor(
    private apiService: ApiService,
    private wsService: WebSocketService,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.load();
    this.wsService.notification$.subscribe((n) => {
      // Other real-time events (e.g. feed updates) share this socket.
      if (!n || typeof n.id !== 'number' || String(n.type ?? '').includes('.')) return;
      // Grouped notifications ("Thandi and 3 others...") arrive again with the same id.
      this.notifications = [n, ...this.notifications.filter((x) => x.id !== n.id)];
    });
    this.wsService.unreadCount$.next(0);
  }

  load(): void {
    this.loading = true;
    this.apiService.getNotifications().subscribe({
      next: (res) => {
        this.notifications = res.results;
        this.loading = false;
      },
      error: () => (this.loading = false),
    });
  }

  markRead(n: Notification): void {
    if (!n.is_read) {
      this.apiService.markNotificationRead(n.id).subscribe(() => (n.is_read = true));
    }
    const link = this.getNavLink(n);
    if (link) this.router.navigate([link]);
  }

  getNavLink(n: Notification): string | null {
    const extra = n.extra ?? {};
    const id = (key: string) => (typeof extra[key] === 'number' ? extra[key] : null);
    if (id('post_id') !== null && ['like', 'comment', 'mention', 'post_share'].includes(n.notification_type)) {
      return `/posts/${id('post_id')}`;
    }
    if (n.notification_type === 'system') {
      switch (extra['kind']) {
        case 'price_drop': return id('listing_id') !== null ? `/marketplace/${id('listing_id')}` : '/marketplace';
        case 'listing_digest': return '/marketplace';
        case 'new_video': return id('video_id') !== null ? `/watch/${id('video_id')}` : '/watch';
        default: return id('listing_id') !== null ? `/marketplace/${id('listing_id')}` : null;
      }
    }
    switch (n.notification_type) {
      case 'friend_request': return '/friends';
      case 'friend_accepted':
      case 'follow':
        return n.sender ? `/profile/${n.sender.username}` : null;
      case 'message': return '/chat';
      default: return null;
    }
  }

  markAllRead(): void {
    this.apiService.markAllNotificationsRead().subscribe(() => {
      this.notifications.forEach((n) => (n.is_read = true));
    });
  }

  getIcon(type: string, extra?: Record<string, unknown>): string {
    if (type === 'system') {
      const kind = extra?.['kind'];
      if (kind === 'price_drop' || kind === 'listing_digest' || extra?.['listing_id']) return 'storefront';
      if (kind === 'new_video') return 'smart_display';
      if (kind === 'moderation') return 'gpp_maybe';
    }
    const map: Record<string, string> = {
      like: 'thumb_up', comment: 'comment', friend_request: 'person_add',
      friend_accepted: 'people', follow: 'person_add_alt', message: 'chat',
      group_invite: 'group_add', post_share: 'share', mention: 'alternate_email',
      system: 'info',
    };
    return map[type] || 'notifications';
  }

  timeAgo(dateStr: string): string {
    const diff = (Date.now() - new Date(dateStr).getTime()) / 1000;
    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  }
}
