import { Injectable } from '@angular/core';
import { Subject, BehaviorSubject } from 'rxjs';
import { environment } from '../../../environments/environment';
import { AuthService } from './auth.service';
import { ApiService } from './api.service';
import { Notification } from '../../models/notification.model';
import { Message, ReactionEvent, ReactionKey, StatusEvent, TypingEvent } from '../../models/chat.model';

const MAX_BACKOFF_MS = 30_000;
// Close codes after which reconnecting can't help: not signed in, or not a member any more.
const FINAL_CHAT_CLOSE_CODES = new Set([4001, 4003]);

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
  private chatRetries = 0;
  private chatReconnectTimer: ReturnType<typeof setTimeout> | null = null;

  notification$ = new Subject<Notification>();
  unreadCount$ = new BehaviorSubject<number>(0);
  /** Ids of friends' new posts, for the feed's "new posts" pill. */
  feedNewPost$ = new Subject<number>();
  chatMessage$ = new Subject<Message>();
  typing$ = new Subject<TypingEvent>();
  chatError$ = new Subject<{ code: string; detail: string }>();
  /** Conversations with unread messages, for the navbar badge. */
  chatUnread$ = new BehaviorSubject<number>(0);

  messageUpdated$ = new Subject<Message>();
  reaction$ = new Subject<ReactionEvent>();
  read$ = new Subject<{ message_id: number; user_id: number }>();
  status$ = new Subject<StatusEvent>();
  presence$ = new Subject<number[]>();
  roomUpdated$ = new Subject<number>();
  memberRemoved$ = new Subject<number>();
  /** Emits the room id when the chat socket comes back after a drop, so the window can catch up. */
  chatReconnected$ = new Subject<number>();

  constructor(private authService: AuthService, private apiService: ApiService) {}

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
          if (data?.notification_type === 'message') this.refreshChatUnread();
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

  refreshChatUnread(): void {
    if (!this.authService.isLoggedIn()) return;
    this.apiService.getChatUnread().subscribe({
      next: (u) => this.chatUnread$.next(u.rooms_with_unread),
      error: () => {},
    });
  }

  connectChat(roomId: number): void {
    this.disconnectChat();
    this.chatRoomId = roomId;
    this.chatRetries = 0;
    this.openChat(roomId, false);
  }

  private openChat(roomId: number, isReconnect: boolean): void {
    this.open(`/chat/${roomId}/`, (ws) => {
      if (this.chatRoomId !== roomId) {
        ws.close();
        return;
      }
      this.chatSocket = ws;
      ws.onopen = () => {
        this.chatRetries = 0;
        if (isReconnect) this.chatReconnected$.next(roomId);
      };
      ws.onmessage = (event) => this.dispatchChatFrame(event.data);
      ws.onclose = (event) => {
        if (this.chatSocket === ws) this.chatSocket = null;
        if (FINAL_CHAT_CLOSE_CODES.has(event.code)) {
          if (event.code === 4003 && this.chatRoomId === roomId) this.memberRemoved$.next(-1);
          return;
        }
        this.scheduleChatReconnect(roomId);
      };
    }, () => this.scheduleChatReconnect(roomId));
  }

  private scheduleChatReconnect(roomId: number): void {
    if (this.chatRoomId !== roomId || !this.authService.isLoggedIn()) return;
    const delay = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** this.chatRetries++);
    if (this.chatRetries === 3) this.chatError$.next({ code: 'connect_failed', detail: 'Reconnecting to chat...' });
    this.chatReconnectTimer = setTimeout(() => {
      this.chatReconnectTimer = null;
      if (this.chatRoomId === roomId) this.openChat(roomId, true);
    }, delay);
  }

  private dispatchChatFrame(raw: string): void {
    let data: { type?: string; [key: string]: unknown };
    try {
      data = JSON.parse(raw);
    } catch {
      return;
    }
    switch (data.type) {
      case 'message':
        this.chatMessage$.next(data['message'] as Message);
        break;
      case 'message_updated':
        this.messageUpdated$.next(data['message'] as Message);
        break;
      case 'reaction':
        this.reaction$.next(data as unknown as ReactionEvent);
        break;
      case 'typing':
        this.typing$.next(data as unknown as TypingEvent);
        break;
      case 'read':
        this.read$.next(data as unknown as { message_id: number; user_id: number });
        break;
      case 'status':
        this.status$.next(data as unknown as StatusEvent);
        break;
      case 'presence':
        this.presence$.next((data['online'] as number[]) ?? []);
        break;
      case 'room_updated':
        this.roomUpdated$.next(data['room_id'] as number);
        break;
      case 'member_removed':
        this.memberRemoved$.next(data['user_id'] as number);
        break;
      case 'error':
        this.chatError$.next({ code: String(data['code'] ?? ''), detail: String(data['detail'] ?? '') });
        break;
    }
  }

  private sendChat(frame: Record<string, unknown>): boolean {
    if (this.chatSocket?.readyState === WebSocket.OPEN) {
      this.chatSocket.send(JSON.stringify(frame));
      return true;
    }
    return false;
  }

  sendChatMessage(content: string, replyTo?: number | null): boolean {
    return this.sendChat({ type: 'message', content, reply_to: replyTo ?? undefined });
  }

  editMessage(messageId: number, content: string): boolean {
    return this.sendChat({ type: 'edit', message_id: messageId, content });
  }

  deleteMessage(messageId: number): boolean {
    return this.sendChat({ type: 'delete', message_id: messageId });
  }

  /** Set, change or (with null) clear your reaction. */
  reactToMessage(messageId: number, reaction: ReactionKey | null): boolean {
    return this.sendChat({ type: 'react', message_id: messageId, reaction });
  }

  sendTyping(isTyping: boolean): void {
    this.sendChat({ type: 'typing', is_typing: isTyping });
  }

  markMessageRead(messageId: number): void {
    this.sendChat({ type: 'read', message_id: messageId });
  }

  disconnectChat(): void {
    this.chatRoomId = null;
    if (this.chatReconnectTimer) clearTimeout(this.chatReconnectTimer);
    this.chatReconnectTimer = null;
    const ws = this.chatSocket;
    this.chatSocket = null;
    ws?.close();
  }

  disconnect(): void {
    this.notificationsWanted = false;
    this.notificationSocket?.close();
    this.notificationSocket = null;
    this.disconnectChat();
    this.chatUnread$.next(0);
  }
}
