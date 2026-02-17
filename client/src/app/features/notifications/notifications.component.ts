import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../core/services/api.service';
import { WebSocketService } from '../../core/services/websocket.service';
import { Notification } from '../../models/notification.model';

@Component({
  selector: 'app-notifications',
  standalone: true,
  imports: [CommonModule, RouterLink, MatIconModule, MatButtonModule, MatProgressSpinnerModule],
  templateUrl: './notifications.component.html',
  styleUrls: ['./notifications.component.scss'],
})
export class NotificationsComponent implements OnInit {
  notifications: Notification[] = [];
  loading = false;

  constructor(private apiService: ApiService, private wsService: WebSocketService) {}

  ngOnInit(): void {
    this.load();
    this.wsService.notification$.subscribe((n) => {
      this.notifications.unshift(n);
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
  }

  markAllRead(): void {
    this.apiService.markAllNotificationsRead().subscribe(() => {
      this.notifications.forEach((n) => (n.is_read = true));
    });
  }

  getIcon(type: string): string {
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
