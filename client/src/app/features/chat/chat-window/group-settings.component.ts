import { ChangeDetectionStrategy, Component, EventEmitter, Input, OnChanges, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatMenuModule } from '@angular/material/menu';
import { ApiService } from '../../../core/services/api.service';
import { ChatMember, ChatRoom } from '../../../models/chat.model';
import { User } from '../../../models/user.model';

/** Group chat settings: name, picture, members and roles. The server enforces who may do what. */
@Component({
  selector: 'app-group-settings',
  imports: [CommonModule, FormsModule, MatIconModule, MatButtonModule, MatMenuModule],
  changeDetection: ChangeDetectionStrategy.Eager,
  template: `
    <div class="panel" role="region" aria-label="Group settings">
      <div class="head">
        <strong>Group settings</strong>
        <button mat-icon-button (click)="closed.emit()" aria-label="Close settings"><mat-icon>close</mat-icon></button>
      </div>
      <p class="error" *ngIf="error">{{ error }}</p>

      <ng-container *ngIf="isAdmin">
        <label class="label" for="group-name">Name</label>
        <div class="row">
          <input id="group-name" class="field" [(ngModel)]="name" maxlength="255" (keyup.enter)="rename()" />
          <button mat-stroked-button (click)="rename()" [disabled]="!name.trim() || name.trim() === room.name">Save</button>
        </div>

        <div class="label">Picture</div>
        <div class="row">
          <img [src]="room.avatar || 'assets/default-avatar.png'" class="avatar md" alt="Group picture" />
          <label class="upload">
            <input type="file" accept="image/jpeg,image/png,image/webp,image/gif" (change)="setAvatar($event)" hidden />
            <span mat-stroked-button>Change</span>
          </label>
          <button mat-button *ngIf="room.avatar" (click)="removeAvatar()">Remove</button>
        </div>
      </ng-container>

      <div class="label">Members ({{ room.members.length }})</div>
      <div class="member" *ngFor="let m of room.members">
        <img [src]="m.user.avatar_url || 'assets/default-avatar.png'" class="avatar sm" [alt]="m.user.username" />
        <span class="who">{{ m.user.full_name }} <span class="role" *ngIf="m.role === 'admin'">Admin</span></span>
        <button mat-icon-button *ngIf="isAdmin && m.user.id !== currentUserId" [matMenuTriggerFor]="memberMenu"
                [attr.aria-label]="'Manage ' + m.user.username">
          <mat-icon>more_vert</mat-icon>
        </button>
        <mat-menu #memberMenu="matMenu">
          <button mat-menu-item *ngIf="m.role !== 'admin'" (click)="setRole(m, 'admin')">Make admin</button>
          <button mat-menu-item *ngIf="m.role === 'admin'" (click)="setRole(m, 'member')">Remove as admin</button>
          <button mat-menu-item (click)="remove(m)">Remove from group</button>
        </mat-menu>
      </div>

      <ng-container *ngIf="isAdmin">
        <div class="label">Add people</div>
        <input class="field" placeholder="Search people..." [(ngModel)]="query" (ngModelChange)="search()" />
        <div class="member" *ngFor="let u of candidates">
          <img [src]="u.avatar_url || 'assets/default-avatar.png'" class="avatar sm" [alt]="u.username" />
          <span class="who">{{ u.full_name }}</span>
          <button mat-icon-button (click)="add(u)" [attr.aria-label]="'Add ' + u.username"><mat-icon>person_add</mat-icon></button>
        </div>
      </ng-container>

      <button mat-stroked-button color="warn" class="leave" (click)="leave()">Leave group</button>
    </div>
  `,
  styles: [`
    .panel { margin: 8px 12px 0; padding: 12px 14px; border-radius: 12px; background: var(--bg-secondary, #f0f2f5);
             font-size: 14px; max-height: 50vh; overflow-y: auto; }
    .head { display: flex; justify-content: space-between; align-items: center; }
    .label { font-size: 12px; text-transform: uppercase; letter-spacing: .04em; opacity: .7; margin: 10px 0 4px; display: block; }
    .row { display: flex; align-items: center; gap: 8px; }
    .field { flex: 1; width: 100%; border: 1px solid var(--border); border-radius: 8px; padding: 6px 10px;
             background: var(--surface); color: var(--text-primary); }
    .member { display: flex; align-items: center; gap: 8px; padding: 4px 0; }
    .who { flex: 1; }
    .role { font-size: 11px; padding: 1px 6px; border-radius: 8px; background: var(--primary-strong); color: var(--on-primary); margin-left: 4px; }
    .upload span { cursor: pointer; text-decoration: underline; }
    .leave { margin-top: 12px; }
    .error { color: var(--danger, #e41e3f); }
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
