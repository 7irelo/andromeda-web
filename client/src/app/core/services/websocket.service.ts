import { Injectable } from '@angular/core';
import { Subject, BehaviorSubject } from 'rxjs';
import { environment } from '../../../environments/environment';
import { AuthService } from './auth.service';
import { Notification } from '../../models/notification.model';

@Injectable({ providedIn: 'root' })
export class WebSocketService {
  private notificationSocket: WebSocket | null = null;
  private chatSocket: WebSocket | null = null;

  notification$ = new Subject<Notification>();
  unreadCount$ = new BehaviorSubject<number>(0);
  chatMessage$ = new Subject<unknown>();
  typing$ = new Subject<unknown>();

  constructor(private authService: AuthService) {}

  connectNotifications(): void {
    if (this.notificationSocket?.readyState === WebSocket.OPEN) return;

    const token = this.authService.getAccessToken();
    const url = `${environment.wsUrl}/notifications/?token=${token}`;

    this.notificationSocket = new WebSocket(url);

    this.notificationSocket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.notification$.next(data);
      this.unreadCount$.next(this.unreadCount$.value + 1);
    };

    this.notificationSocket.onerror = (err) => console.error('Notification WS error', err);

    this.notificationSocket.onclose = () => {
      // Auto-reconnect after 5s if still logged in
      setTimeout(() => {
        if (this.authService.isLoggedIn()) this.connectNotifications();
      }, 5000);
    };
  }

  connectChat(roomId: number): void {
    this.disconnectChat();
    const token = this.authService.getAccessToken();
    const url = `${environment.wsUrl}/chat/${roomId}/?token=${token}`;
    this.chatSocket = new WebSocket(url);

    this.chatSocket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'message') {
        this.chatMessage$.next(data);
      } else if (data.type === 'typing') {
        this.typing$.next(data);
      }
    };

    this.chatSocket.onerror = (err) => console.error('Chat WS error', err);
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
    this.chatSocket?.close();
    this.chatSocket = null;
  }

  disconnect(): void {
    this.notificationSocket?.close();
    this.notificationSocket = null;
    this.disconnectChat();
  }
}
