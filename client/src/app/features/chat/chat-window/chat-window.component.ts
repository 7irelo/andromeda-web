import {
  Component, OnInit, OnDestroy, OnChanges, SimpleChanges, Input, ViewChild, ElementRef, AfterViewChecked,
  ChangeDetectionStrategy,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { MatDialog } from '@angular/material/dialog';
import { openReportDialog } from '../../../shared/components/report-dialog/report-dialog.component';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Subscription } from 'rxjs';
import { ApiService } from '../../../core/services/api.service';
import { AuthService } from '../../../core/services/auth.service';
import { WebSocketService } from '../../../core/services/websocket.service';
import { CatchUp, Message, ChatRoom, REACTIONS, ReactionKey } from '../../../models/chat.model';
import { User } from '../../../models/user.model';
import { VoiceNoteComponent } from './voice-note.component';
import { GroupSettingsComponent } from './group-settings.component';
import { SmartRepliesComponent } from './smart-replies.component';

const MAX_VOICE_SECONDS = 300;
// Preferred first: Chrome/Firefox record WebM/Opus, Firefox also Ogg, Safari only MP4.
const VOICE_MIME_TYPES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/ogg', 'audio/mp4'];
const VOICE_EXT: Record<string, string> = { 'audio/webm': 'webm', 'audio/ogg': 'ogg', 'audio/mp4': 'm4a' };

@Component({
    selector: 'app-chat-window',
    imports: [CommonModule, FormsModule, MatIconModule, MatButtonModule, MatMenuModule, MatTooltipModule,
        VoiceNoteComponent, GroupSettingsComponent, SmartRepliesComponent],
    templateUrl: './chat-window.component.html',
    changeDetection: ChangeDetectionStrategy.Eager,
    styleUrls: ['./chat-window.component.scss']
})
export class ChatWindowComponent implements OnInit, OnChanges, OnDestroy, AfterViewChecked {
  @Input() roomId!: string;
  @ViewChild('messagesEnd') messagesEnd!: ElementRef;
  @ViewChild(SmartRepliesComponent) smartReplies?: SmartRepliesComponent;

  readonly reactions = REACTIONS;
  room: ChatRoom | null = null;
  messages: Message[] = [];
  messageText = '';
  loading = false;
  currentUser: User | null = null;
  typingUsers: string[] = [];
  onlineIds = new Set<number>();
  notice = '';
  removed = false;
  private subs = new Subscription();
  private scrollPending = false;
  private noticeTimer: ReturnType<typeof setTimeout> | null = null;

  summary: CatchUp | null = null;
  catchingUp = false;
  catchUpError = '';

  replyingTo: Message | null = null;
  editing: Message | null = null;
  highlightId: number | null = null;

  showSearch = false;
  searchQuery = '';
  searchResults: Message[] | null = null;
  searching = false;

  showSettings = false;

  /** Bumped on each new incoming message, so smart replies can offer suggestions. */
  incomingTick = 0;

  recording = false;
  recordSeconds = 0;
  uploadingVoice = false;
  private recorder: MediaRecorder | null = null;
  private recordTimer: ReturnType<typeof setInterval> | null = null;
  private discardRecording = false;

  constructor(
    private apiService: ApiService,
    private authService: AuthService,
    private wsService: WebSocketService,
    private router: Router,
    private dialog: MatDialog,
  ) {}

  reportMessage(msg: Message): void {
    openReportDialog(this.dialog, { type: 'message', id: msg.id, label: 'message' });
  }

  get id(): number {
    return parseInt(this.roomId, 10);
  }

  catchUp(): void {
    this.catchingUp = true;
    this.catchUpError = '';
    this.apiService.catchUp(this.id).subscribe({
      next: (s) => {
        this.summary = s;
        this.catchingUp = false;
      },
      error: (err) => {
        this.catchingUp = false;
        this.catchUpError = err?.status === 429
          ? "You've used your summaries for now. Try again later."
          : err?.error?.detail ?? 'Summaries are unavailable right now.';
      },
    });
  }

  ngOnChanges(changes: SimpleChanges): void {
    // The router reuses this component when switching between rooms.
    if (changes['roomId'] && !changes['roomId'].firstChange) this.openRoom();
  }

  private openRoom(): void {
    this.stopRecording(false);
    Object.assign(this, {
      room: null, messages: [], messageText: '', typingUsers: [], onlineIds: new Set<number>(), removed: false,
      summary: null, catchUpError: '', replyingTo: null, editing: null, showSearch: false, searchResults: null,
      showSettings: false,
    });
    this.wsService.connectChat(this.id);
    this.loadRoom();
    this.loadMessages(this.id);
  }

  ngOnInit(): void {
    this.currentUser = this.authService.currentUser;
    this.openRoom();

    this.subs.add(this.wsService.chatMessage$.subscribe((m) => {
      if (m.room !== this.id) return;
      this.upsert(m);
      this.scrollPending = true;
      if (!this.isMyMessage(m)) {
        this.wsService.markMessageRead(m.id);
        this.markRead();
        if (!m.is_deleted) this.incomingTick++;
      }
    }));
    this.subs.add(this.wsService.messageUpdated$.subscribe((m) => {
      if (m.room !== this.id) return;
      const existing = this.messages.find((x) => x.id === m.id);
      // Broadcasts carry no viewer-specific fields: keep our own reaction.
      this.upsert({ ...m, my_reaction: m.is_deleted ? null : existing?.my_reaction ?? null });
      if (this.editing?.id === m.id && m.is_deleted) this.cancelEdit();
      if (this.replyingTo?.id === m.id && m.is_deleted) this.replyingTo = null;
    }));
    this.subs.add(this.wsService.reaction$.subscribe((r) => {
      const i = this.messages.findIndex((x) => x.id === r.message_id);
      if (i < 0) return;
      const m = this.messages[i];
      const mine = r.user_id === this.currentUser?.id ? r.reaction : m.my_reaction;
      this.messages[i] = { ...m, reactions: r.reactions, my_reaction: mine };
    }));
    this.subs.add(this.wsService.typing$.subscribe((t) => {
      if (t.is_typing) {
        if (!this.typingUsers.includes(t.username)) this.typingUsers.push(t.username);
      } else {
        this.typingUsers = this.typingUsers.filter((u) => u !== t.username);
      }
    }));
    this.subs.add(this.wsService.presence$.subscribe((ids) => (this.onlineIds = new Set(ids))));
    this.subs.add(this.wsService.status$.subscribe((s) => {
      const next = new Set(this.onlineIds);
      if (s.status === 'online') next.add(s.user_id);
      else next.delete(s.user_id);
      this.onlineIds = next;
    }));
    this.subs.add(this.wsService.roomUpdated$.subscribe(() => this.loadRoom()));
    this.subs.add(this.wsService.memberRemoved$.subscribe((userId) => {
      if (userId === -1 || userId === this.currentUser?.id) {
        this.removed = true;
        this.stopRecording(false);
      } else {
        this.loadRoom();
      }
    }));
    this.subs.add(this.wsService.chatError$.subscribe((e) => this.showNotice(e.detail)));
    this.subs.add(this.wsService.chatReconnected$.subscribe((roomId) => {
      if (roomId === this.id) this.catchUpMissed();
    }));
  }

  ngAfterViewChecked(): void {
    if (this.scrollPending) {
      this.scrollPending = false;
      this.scrollToBottom();
    }
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
    this.stopRecording(false);
    if (this.noticeTimer) clearTimeout(this.noticeTimer);
    this.wsService.disconnectChat();
  }

  // ── Loading ─────────────────────────────────────────────────────────

  loadRoom(): void {
    this.apiService.getChatRoom(this.id).subscribe({
      next: (room) => (this.room = room),
      error: (err) => {
        if (err?.status === 404) this.removed = true;
      },
    });
  }

  loadMessages(roomId: number): void {
    this.loading = true;
    this.apiService.getRoomMessages(roomId).subscribe({
      next: (res) => {
        this.messages = res.results.reverse();
        this.loading = false;
        this.scrollPending = true;
        this.markRead();
      },
      error: () => (this.loading = false),
    });
  }

  /** After a dropped socket comes back: fetch everything newer than the last message we have. */
  private catchUpMissed(): void {
    const lastId = this.messages.reduce((max, m) => Math.max(max, m.id), 0);
    if (!lastId) {
      this.loadMessages(this.id);
      return;
    }
    this.apiService.getRoomMessagesAfter(this.id, lastId).subscribe({
      next: (res) => {
        res.results.forEach((m) => this.upsert(m));
        if (res.results.length) this.scrollPending = true;
        if (res.has_more) this.catchUpMissed();
        else this.markRead();
      },
    });
    this.loadRoom();
    this.apiService.getRoomPresence(this.id).subscribe({ next: (p) => (this.onlineIds = new Set(p.online)) });
  }

  private markRead(): void {
    this.apiService.markRoomRead(this.id).subscribe({ next: () => this.wsService.refreshChatUnread() });
  }

  private upsert(m: Message): void {
    const i = this.messages.findIndex((x) => x.id === m.id);
    if (i >= 0) {
      this.messages[i] = m;
      return;
    }
    // Keep id order: a REST response and its broadcast can arrive either way round.
    const at = this.messages.findIndex((x) => x.id > m.id);
    if (at < 0) this.messages.push(m);
    else this.messages.splice(at, 0, m);
  }

  // ── Sending, replying, editing ──────────────────────────────────────

  sendMessage(): void {
    const text = this.messageText.trim();
    if (!text) return;
    if (this.editing) {
      if (text !== this.editing.content && !this.wsService.editMessage(this.editing.id, text)) {
        this.showNotice('Not connected. Try again in a moment.');
        return;
      }
      this.cancelEdit();
      return;
    }
    if (!this.wsService.sendChatMessage(text, this.replyingTo?.id)) {
      this.showNotice('Not connected. Try again in a moment.');
      return;
    }
    this.messageText = '';
    this.replyingTo = null;
    this.wsService.sendTyping(false);
    this.smartReplies?.noteSent(text);
  }

  useSuggestion(text: string): void {
    this.messageText = text;
  }

  onTyping(): void {
    if (!this.editing) this.wsService.sendTyping(true);
  }

  startReply(msg: Message): void {
    this.cancelEdit();
    this.replyingTo = msg;
  }

  startEdit(msg: Message): void {
    this.replyingTo = null;
    this.editing = msg;
    this.messageText = msg.content;
  }

  cancelEdit(): void {
    if (this.editing) this.messageText = '';
    this.editing = null;
  }

  deleteMessage(msg: Message): void {
    if (!confirm('Delete this message for everyone?')) return;
    if (!this.wsService.deleteMessage(msg.id)) this.showNotice('Not connected. Try again in a moment.');
  }

  react(msg: Message, key: ReactionKey): void {
    this.wsService.reactToMessage(msg.id, msg.my_reaction === key ? null : key);
  }

  emoji(key: ReactionKey): string {
    return REACTIONS.find((r) => r.key === key)?.emoji ?? '';
  }

  canEdit(msg: Message): boolean {
    return this.isMyMessage(msg) && !msg.is_deleted && msg.message_type === 'text';
  }

  isMyMessage(msg: Message): boolean {
    return msg.sender?.id === this.currentUser?.id;
  }

  quote(data: Message['reply_to_data']): string {
    if (!data) return '';
    if (data.is_deleted) return 'message deleted';
    if (data.message_type === 'voice') return 'Voice message';
    return data.content || 'Attachment';
  }

  jumpTo(messageId: number): void {
    const el = document.getElementById(`msg-${messageId}`);
    if (!el) {
      this.showNotice('That message is further back in the conversation.');
      return;
    }
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    this.highlightId = messageId;
    setTimeout(() => (this.highlightId = null), 1600);
  }

  // ── Search ──────────────────────────────────────────────────────────

  toggleSearch(): void {
    this.showSearch = !this.showSearch;
    this.searchResults = null;
    this.searchQuery = '';
  }

  runSearch(): void {
    const q = this.searchQuery.trim();
    if (q.length < 2) return;
    this.searching = true;
    this.apiService.searchRoomMessages(this.id, q).subscribe({
      next: (res) => {
        this.searchResults = res.results;
        this.searching = false;
      },
      error: () => {
        this.searchResults = [];
        this.searching = false;
      },
    });
  }

  // ── Voice notes ─────────────────────────────────────────────────────

  get recordLabel(): string {
    const s = this.recordSeconds;
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  }

  async startRecording(): Promise<void> {
    if (this.recording || this.uploadingVoice) return;
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      this.showNotice('Voice messages are not supported in this browser.');
      return;
    }
    const mimeType = VOICE_MIME_TYPES.find((t) => MediaRecorder.isTypeSupported(t));
    if (!mimeType) {
      this.showNotice('Voice messages are not supported in this browser.');
      return;
    }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      this.showNotice('Allow microphone access to record a voice message.');
      return;
    }
    const chunks: Blob[] = [];
    const recorder = new MediaRecorder(stream, { mimeType, audioBitsPerSecond: 32_000 });
    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    recorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      if (!this.discardRecording && chunks.length) {
        this.uploadVoice(new Blob(chunks, { type: mimeType.split(';')[0] }));
      }
    };
    this.discardRecording = false;
    this.recorder = recorder;
    this.recording = true;
    this.recordSeconds = 0;
    const started = Date.now();
    recorder.start(1000);
    this.recordTimer = setInterval(() => {
      this.recordSeconds = Math.floor((Date.now() - started) / 1000);
      // The server refuses anything over five minutes; stop just short of it.
      if (this.recordSeconds >= MAX_VOICE_SECONDS - 1) this.stopRecording(true);
    }, 250);
  }

  stopRecording(send: boolean): void {
    if (this.recordTimer) clearInterval(this.recordTimer);
    this.recordTimer = null;
    if (!this.recorder) return;
    this.discardRecording = !send;
    if (this.recorder.state !== 'inactive') this.recorder.stop();
    this.recorder = null;
    this.recording = false;
  }

  private uploadVoice(blob: Blob): void {
    const ext = VOICE_EXT[blob.type] ?? 'webm';
    this.uploadingVoice = true;
    this.apiService.sendVoiceNote(this.id, blob, `voice.${ext}`, this.replyingTo?.id).subscribe({
      next: (m) => {
        this.uploadingVoice = false;
        this.replyingTo = null;
        this.upsert(m);
        this.scrollPending = true;
      },
      error: (err) => {
        this.uploadingVoice = false;
        this.showNotice(err?.error?.file?.[0] ?? err?.error?.detail ?? 'Could not send the voice message.');
      },
    });
  }

  // ── Room ────────────────────────────────────────────────────────────

  get title(): string {
    if (!this.room) return '';
    if (this.room.name) return this.room.name;
    const other = this.room.members.find((m) => m.user.id !== this.currentUser?.id);
    return this.room.room_type === 'direct' ? other?.user.full_name ?? 'Chat' : 'Group Chat';
  }

  get presenceLabel(): string {
    if (!this.room) return '';
    const others = this.room.members.filter((m) => m.user.id !== this.currentUser?.id);
    const online = others.filter((m) => this.onlineIds.has(m.user.id)).length;
    if (this.room.room_type === 'direct') return online ? 'Active now' : '';
    return online ? `${online} online` : `${this.room.members.length} members`;
  }

  isOnline(userId: number | undefined): boolean {
    return userId !== undefined && this.onlineIds.has(userId);
  }

  onRoomChanged(room: ChatRoom | null): void {
    if (room) this.room = room;
    else this.loadRoom();
  }

  onLeft(): void {
    this.router.navigate(['/chat']);
  }

  private showNotice(text: string): void {
    this.notice = text;
    if (this.noticeTimer) clearTimeout(this.noticeTimer);
    this.noticeTimer = setTimeout(() => (this.notice = ''), 5000);
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
