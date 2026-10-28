import { Injectable } from '@angular/core';
import { Subject, BehaviorSubject } from 'rxjs';
import { environment } from '../../../environments/environment';
import { AuthService } from './auth.service';
import { Notification } from '../../models/notification.model';

const MAX_BACKOFF_MS = 30_000;

/**
 * WebSockets authenticate with a single-use ticket fetched over HTTPS
 * immediately before each connection. Tokens never appear in socket URLs.
 */
@Injectable({ providedIn: 'root' })
export class WebSocketService {
  private notificationSocket: WebSocket | null = null;
  private chatSocket: WebSocket | null = null;
  private notificationRetries = 0;
  private notificationsWanted = false;
  private chatRoomId: number | null = null;

  notification$ = new Subject<Notification>();
  unreadCount$ = new BehaviorSubject<number>(0);
  /** Ids of friends' new posts, for the feed's "new posts" pill. */
  feedNewPost$ = new Subject<number>();
  chatMessage$ = new Subject<unknown>();
  typing$ = new Subject<unknown>();
  chatError$ = new Subject<{ code: string; detail: string }>();

  constructor(private authService: AuthService) {}

  private open(path: string, onOpen: (ws: WebSocket) => void, onFail: () => void): void {
    this.authService.getWebSocketTicket().subscribe({
      next: (ticket) => onOpen(new WebSocket(`${environment.wsUrl}${path}?ticket=${encodeURIComponent(ticket)}`)),
      error: onFail,
    });
  }

  connectNotifications(): void {
    this.notificationsWanted = true;
    if (this.notificationSocket && this.notificationSocket.readyState <= WebSocket.OPEN) return;

    this.open('/notifications/', (ws) => {
      this.notificationSocket = ws;
      ws.onopen = () => (this.notificationRetries = 0);
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          // Feed events carry only a post id; they are not notifications and don't touch the badge.
          if (data?.type === 'feed.new_post') {
            if (typeof data.post_id === 'number') this.feedNewPost$.next(data.post_id);
            return;
          }
          this.notification$.next(data);
          this.unreadCount$.next(this.unreadCount$.value + 1);
        } catch {
          /* ignore malformed frames */
        }
      };
      ws.onclose = () => this.scheduleNotificationReconnect();
    }, () => this.scheduleNotificationReconnect());
  }

  private scheduleNotificationReconnect(): void {
    this.notificationSocket = null;
    if (!this.notificationsWanted || !this.authService.isLoggedIn()) return;
    const delay = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** this.notificationRetries++);
    setTimeout(() => this.connectNotifications(), delay);
  }

  connectChat(roomId: number): void {
    this.disconnectChat();
    this.chatRoomId = roomId;
    this.open(`/chat/${roomId}/`, (ws) => {
      if (this.chatRoomId !== roomId) {
        ws.close();
        return;
      }
      this.chatSocket = ws;
      ws.onmessage = (event) => {
        let data: { type?: string; code?: string; detail?: string };
        try {
          data = JSON.parse(event.data);
        } catch {
          return;
        }
        if (data.type === 'message') this.chatMessage$.next(data);
        else if (data.type === 'typing') this.typing$.next(data);
        else if (data.type === 'error') this.chatError$.next({ code: data.code ?? '', detail: data.detail ?? '' });
      };
    }, () => this.chatError$.next({ code: 'connect_failed', detail: 'Could not connect to chat.' }));
  }

  sendChatMessage(content: string, replyTo?: number): void {
    if (this.chatSocket?.readyState === WebSocket.OPEN) {
      this.chatSocket.send(JSON.stringify({ type: 'message', content, reply_to: replyTo }));
    }
  }

  sendTyping(isTyping: boolean): void {
    if (this.chatSocket?.readyState === WebSocket.OPEN) {
      this.chatSocket.send(JSON.stringify({ type: 'typing', is_typing: isTyping }));
    }
  }

  markMessageRead(messageId: number): void {
    if (this.chatSocket?.readyState === WebSocket.OPEN) {
      this.chatSocket.send(JSON.stringify({ type: 'read', message_id: messageId }));
    }
  }

  disconnectChat(): void {
    this.chatRoomId = null;
    this.chatSocket?.close();
    this.chatSocket = null;
  }

  disconnect(): void {
    this.notificationsWanted = false;
    this.notificationSocket?.close();
    this.notificationSocket = null;
    this.disconnectChat();
  }
}
