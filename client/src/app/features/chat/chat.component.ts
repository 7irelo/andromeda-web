import { Component, OnInit, OnDestroy, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet, RouterLink, Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatInputModule } from '@angular/material/input';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { WebSocketService } from '../../core/services/websocket.service';
import { Subscription } from 'rxjs';
import { ChatRoom } from '../../models/chat.model';
import { User } from '../../models/user.model';

@Component({
    selector: 'app-chat',
    imports: [CommonModule, RouterOutlet, RouterLink, FormsModule, MatIconModule, MatButtonModule, MatInputModule],
    templateUrl: './chat.component.html',
    changeDetection: ChangeDetectionStrategy.Eager,
    styleUrls: ['./chat.component.scss']
})
export class ChatComponent implements OnInit, OnDestroy {
  rooms: ChatRoom[] = [];
  currentUser: User | null = null;
  loading = false;

  // New-message search panel
  showNewChat = false;
  newChatQuery = '';
  newChatResults: User[] = [];
  newChatSearching = false;
  private subs = new Subscription();

  constructor(
    private apiService: ApiService,
    private authService: AuthService,
    private wsService: WebSocketService,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.currentUser = this.authService.currentUser;
    this.loadRooms();
    // Keep the open room's preview fresh and float it to the top.
    this.subs.add(this.wsService.chatMessage$.subscribe((m) => {
      const room = this.rooms.find((r) => r.id === m.room);
      if (!room) return;
      room.last_message = m;
      this.rooms = [room, ...this.rooms.filter((r) => r !== room)];
    }));
    this.subs.add(this.wsService.memberRemoved$.subscribe(() => this.loadRooms()));
    this.subs.add(this.wsService.roomUpdated$.subscribe(() => this.loadRooms()));
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
  }

  preview(room: ChatRoom): string {
    const m = room.last_message;
    if (!m) return 'No messages yet';
    if (m.message_type === 'voice') return 'Voice message';
    return m.content || 'Attachment';
  }

  loadRooms(): void {
    this.loading = true;
    this.apiService.getChatRooms().subscribe({
      next: (res) => {
        this.rooms = res.results;
        this.loading = false;
      },
      error: () => (this.loading = false),
    });
  }

  getRoomName(room: ChatRoom): string {
    if (room.name) return room.name;
    if (room.room_type === 'direct') {
      const other = room.members.find((m) => m.user.id !== this.currentUser?.id);
      return other?.user.full_name ?? 'Chat';
    }
    return 'Group Chat';
  }

  getRoomAvatar(room: ChatRoom): string {
    if (room.avatar) return room.avatar;
    if (room.room_type === 'direct') {
      const other = room.members.find((m) => m.user.id !== this.currentUser?.id);
      return other?.user.avatar_url ?? 'assets/default-avatar.png';
    }
    return 'assets/default-avatar.png';
  }

  openRoom(room: ChatRoom): void {
    room.unread_count = 0;
    this.router.navigate(['/chat', room.id]);
  }

  timeAgo(dateStr: string | undefined): string {
    if (!dateStr) return '';
    const diff = (Date.now() - new Date(dateStr).getTime()) / 1000;
    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
    return new Date(dateStr).toLocaleDateString();
  }

  // ── New message panel ─────────────────────────────────────────────
  openNewChat(): void {
    this.showNewChat = true;
    this.newChatQuery = '';
    this.loadNewChatCandidates('');
  }

  closeNewChat(): void {
    this.showNewChat = false;
  }

  searchNewChatUsers(): void {
    const q = this.newChatQuery.trim();
    this.loadNewChatCandidates(q);
  }

  private loadNewChatCandidates(query: string): void {
    this.newChatSearching = true;
    this.apiService.searchUsers(query).subscribe({
      next: (res) => {
        const users = res.results.filter((u) => u.id !== this.currentUser?.id);
        // When query is empty, prefer friends so starting a DM is fast.
        if (!query) {
          const friends = users.filter((u) => u.is_friend);
          this.newChatResults = friends.length ? friends : users;
        } else {
          this.newChatResults = users;
        }
        this.newChatSearching = false;
      },
      error: () => {
        this.newChatResults = [];
        this.newChatSearching = false;
      },
    });
  }

  startDM(user: User): void {
    this.closeNewChat();
    this.apiService.createChatRoom({ member_ids: [user.id], room_type: 'direct' }).subscribe({
      next: (room) => {
        this.loadRooms();
        this.router.navigate(['/chat', room.id]);
      },
    });
  }
}
