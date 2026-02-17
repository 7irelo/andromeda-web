import { Component, OnInit, OnDestroy, Input, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { Subscription } from 'rxjs';
import { ApiService } from '../../../core/services/api.service';
import { AuthService } from '../../../core/services/auth.service';
import { WebSocketService } from '../../../core/services/websocket.service';
import { Message, ChatRoom } from '../../../models/chat.model';
import { User } from '../../../models/user.model';

@Component({
  selector: 'app-chat-window',
  standalone: true,
  imports: [CommonModule, FormsModule, MatIconModule, MatButtonModule],
  templateUrl: './chat-window.component.html',
  styleUrls: ['./chat-window.component.scss'],
})
export class ChatWindowComponent implements OnInit, OnDestroy, AfterViewChecked {
  @Input() roomId!: string;
  @ViewChild('messagesEnd') messagesEnd!: ElementRef;

  room: ChatRoom | null = null;
  messages: Message[] = [];
  messageText = '';
  loading = false;
  currentUser: User | null = null;
  typingUsers: string[] = [];
  private subs = new Subscription();

  constructor(
    private apiService: ApiService,
    private authService: AuthService,
    private wsService: WebSocketService,
  ) {}

  ngOnInit(): void {
    this.currentUser = this.authService.currentUser;
    const id = parseInt(this.roomId, 10);
    this.wsService.connectChat(id);
    this.loadMessages(id);

    this.subs.add(
      this.wsService.chatMessage$.subscribe((msg: unknown) => {
        const m = msg as Message;
        this.messages.push(m);
        this.apiService.markRoomRead(id).subscribe();
      })
    );

    this.subs.add(
      this.wsService.typing$.subscribe((data: unknown) => {
        const t = data as { username: string; is_typing: boolean };
        if (t.is_typing) {
          if (!this.typingUsers.includes(t.username)) {
            this.typingUsers.push(t.username);
          }
        } else {
          this.typingUsers = this.typingUsers.filter((u) => u !== t.username);
        }
      })
    );
  }

  ngAfterViewChecked(): void {
    this.scrollToBottom();
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
    this.wsService.disconnectChat();
  }

  loadMessages(roomId: number): void {
    this.loading = true;
    this.apiService.getRoomMessages(roomId).subscribe({
      next: (res) => {
        this.messages = res.results.reverse();
        this.loading = false;
        this.apiService.markRoomRead(roomId).subscribe();
      },
      error: () => (this.loading = false),
    });
  }

  sendMessage(): void {
    if (!this.messageText.trim()) return;
    this.wsService.sendChatMessage(this.messageText);
    this.messageText = '';
    this.wsService.sendTyping(false);
  }

  onTyping(): void {
    this.wsService.sendTyping(true);
  }

  isMyMessage(msg: Message): boolean {
    return msg.sender?.id === this.currentUser?.id;
  }

  private scrollToBottom(): void {
    try {
      this.messagesEnd.nativeElement.scrollIntoView({ behavior: 'smooth' });
    } catch {}
  }

  timeLabel(dateStr: string): string {
    return new Date(dateStr).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
}
