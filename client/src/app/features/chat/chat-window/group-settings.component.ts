import { ChangeDetectionStrategy, Component, EventEmitter, Input, OnChanges, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { ApiService } from '../../../core/services/api.service';
import { ChatMember, ChatRoom } from '../../../models/chat.model';
import { User } from '../../../models/user.model';

/** Group chat settings: name, picture, members and roles. The server enforces who may do what. */
@Component({
  selector: 'app-group-settings',
  imports: [CommonModule, FormsModule, MatIconModule, MatMenuModule],
  changeDetection: ChangeDetectionStrategy.Eager,
  template: `
    <div class="panel" role="region" aria-label="Group settings">
      <div class="head">
        <strong>Group settings</strong>
        <button type="button" class="icon-btn" (click)="closed.emit()" aria-label="Close settings"><mat-icon aria-hidden="true">close</mat-icon></button>
      </div>
      <p class="error" *ngIf="error">{{ error }}</p>

      <ng-container *ngIf="isAdmin">
        <label class="label" for="group-name">Name</label>
        <div class="row">
          <input id="group-name" class="field" [(ngModel)]="name" maxlength="255" (keyup.enter)="rename()" />
          <button type="button" class="btn" (click)="rename()" [disabled]="!name.trim() || name.trim() === room.name">Save</button>
        </div>

        <div class="label">Picture</div>
        <div class="row">
          <img [src]="room.avatar || 'assets/default-avatar.png'" class="avatar md" alt="Group picture" />
          <label class="btn upload">
            <input type="file" class="visually-hidden" accept="image/jpeg,image/png,image/webp,image/gif" (change)="setAvatar($event)" />
            <span>Change</span>
          </label>
          <button type="button" class="btn plain" *ngIf="room.avatar" (click)="removeAvatar()">Remove</button>
        </div>
      </ng-container>

      <div class="label">Members ({{ room.members.length }})</div>
      <div class="member" *ngFor="let m of room.members">
        <img [src]="m.user.avatar_url || 'assets/default-avatar.png'" class="avatar sm" [alt]="m.user.username" />
        <span class="who">{{ m.user.full_name }} <span class="role" *ngIf="m.role === 'admin'">Admin</span></span>
        <button type="button" class="icon-btn" *ngIf="isAdmin && m.user.id !== currentUserId" [matMenuTriggerFor]="memberMenu"
                [attr.aria-label]="'Manage ' + m.user.username">
          <mat-icon aria-hidden="true">more_vert</mat-icon>
        </button>
        <mat-menu #memberMenu="matMenu">
          <button mat-menu-item *ngIf="m.role !== 'admin'" (click)="setRole(m, 'admin')">Make admin</button>
          <button mat-menu-item *ngIf="m.role === 'admin'" (click)="setRole(m, 'member')">Remove as admin</button>
          <button mat-menu-item (click)="remove(m)">Remove from group</button>
        </mat-menu>
      </div>

      <ng-container *ngIf="isAdmin">
        <label class="label" for="group-add">Add people</label>
        <input id="group-add" class="field" placeholder="Search people..." [(ngModel)]="query" (ngModelChange)="search()" />
        <div class="member" *ngFor="let u of candidates">
          <img [src]="u.avatar_url || 'assets/default-avatar.png'" class="avatar sm" [alt]="u.username" />
          <span class="who">{{ u.full_name }}</span>
          <button type="button" class="icon-btn" (click)="add(u)" [attr.aria-label]="'Add ' + u.username"><mat-icon aria-hidden="true">person_add</mat-icon></button>
        </div>
      </ng-container>

      <button type="button" class="btn danger leave" (click)="leave()">Leave group</button>
    </div>
  `,
  styles: [`
    .panel { margin: 12px 16px 0; padding: 12px; border: 1px solid var(--border); border-radius: var(--radius-sm);
             background: var(--surface); font-size: 13px; color: var(--text-primary); max-height: 50vh; overflow-y: auto; }
    .head { display: flex; justify-content: space-between; align-items: center; font-size: 14px; }
    .head strong { font-weight: 600; }
    .label { display: block; margin: 12px 0 4px; font-size: 12px; font-weight: 600; color: var(--text-secondary); }
    .row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
    .field { flex: 1; width: 100%; min-width: 0; height: 36px; padding: 0 12px; border: 1px solid var(--border-strong);
             border-radius: var(--radius-sm); background: var(--surface); font: inherit; font-size: 13px; color: var(--text-primary); }
    .row .field { width: auto; flex-basis: 140px; }
    .field::placeholder { color: var(--text-muted); }
    .member { display: flex; align-items: center; gap: 8px; min-height: 40px; }
    .who { flex: 1; min-width: 0; overflow-wrap: anywhere; }
    .role { margin-left: 4px; padding: 0 6px; border: 1px solid var(--border); border-radius: 6px;
            font-size: 11px; color: var(--text-secondary); }
    .icon-btn { display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; width: 36px; height: 36px;
                border: none; border-radius: var(--radius-sm); background: none; color: var(--text-secondary); cursor: pointer; }
    .icon-btn:hover { background: var(--surface-2); color: var(--text-primary); }
    .icon-btn mat-icon { width: 20px; height: 20px; font-size: 20px; }
    .btn { display: inline-flex; align-items: center; justify-content: center; height: 36px; padding: 0 12px;
           border: 1px solid var(--border-strong); border-radius: var(--radius-sm); background: none; font: inherit;
           font-size: 13px; font-weight: 500; color: var(--text-primary); cursor: pointer; }
    .btn:hover:not(:disabled) { background: var(--surface-2); }
    .btn:disabled { border-color: var(--border); color: var(--text-muted); cursor: default; }
    .btn.plain { border-color: transparent; color: var(--primary); }
    .btn.danger { border-color: var(--border); color: var(--danger-text); }
    .upload:focus-within { outline: 3px solid var(--focus-ring-color); outline-offset: 2px; }
    .leave { margin-top: 12px; }
    .error { margin: 8px 0 0; color: var(--danger-text); }
    @media (max-width: 768px) {
      .panel { margin: 8px 12px 0; }
      .field, .btn { height: var(--touch-target); }
      .field { font-size: 16px; }
      .icon-btn { width: var(--touch-target); height: var(--touch-target); }
    }
  `],
})
export class GroupSettingsComponent implements OnChanges {
  @Input({ required: true }) room!: ChatRoom;
  @Input() currentUserId: number | null = null;
  @Output() changed = new EventEmitter<ChatRoom | null>();
  @Output() left = new EventEmitter<void>();
  @Output() closed = new EventEmitter<void>();

  name = '';
  query = '';
  candidates: User[] = [];
  error = '';

  constructor(private apiService: ApiService) {}

  get isAdmin(): boolean {
    return this.room.my_role === 'admin';
  }

  ngOnChanges(): void {
    this.name = this.room.name;
  }

  private fail(err: { error?: { detail?: string; name?: string[]; avatar?: string[] } }): void {
    const e = err?.error;
    this.error = e?.detail ?? e?.name?.[0] ?? e?.avatar?.[0] ?? 'Something went wrong.';
  }

  rename(): void {
    this.error = '';
    this.apiService.renameChatRoom(this.room.id, this.name.trim()).subscribe({
      next: (room) => this.changed.emit(room),
      error: (err) => this.fail(err),
    });
  }

  setAvatar(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    this.error = '';
    this.apiService.setChatRoomAvatar(this.room.id, file).subscribe({
      next: (room) => this.changed.emit(room),
      error: (err) => this.fail(err),
    });
  }

  removeAvatar(): void {
    this.apiService.removeChatRoomAvatar(this.room.id).subscribe({
      next: (room) => this.changed.emit(room),
      error: (err) => this.fail(err),
    });
  }

  setRole(member: ChatMember, role: 'admin' | 'member'): void {
    this.apiService.setChatMemberRole(this.room.id, member.user.id, role).subscribe({
      next: () => this.changed.emit(null),
      error: (err) => this.fail(err),
    });
  }

  remove(member: ChatMember): void {
    if (!confirm(`Remove ${member.user.full_name} from the group?`)) return;
    this.apiService.removeChatMember(this.room.id, member.user.id).subscribe({
      next: () => this.changed.emit(null),
      error: (err) => this.fail(err),
    });
  }

  search(): void {
    const q = this.query.trim();
    if (q.length < 2) {
      this.candidates = [];
      return;
    }
    this.apiService.searchUsers(encodeURIComponent(q)).subscribe({
      next: (res) => {
        const inRoom = new Set(this.room.members.map((m) => m.user.id));
        this.candidates = res.results.filter((u) => !inRoom.has(u.id)).slice(0, 8);
      },
      error: () => (this.candidates = []),
    });
  }

  add(user: User): void {
    this.apiService.addChatMember(this.room.id, user.id).subscribe({
      next: () => {
        this.query = '';
        this.candidates = [];
        this.changed.emit(null);
      },
      error: (err) => this.fail(err),
    });
  }

  leave(): void {
    if (!confirm('Leave this group?')) return;
    this.apiService.leaveChatRoom(this.room.id).subscribe({
      next: () => this.left.emit(),
      error: (err) => this.fail(err),
    });
  }
}
