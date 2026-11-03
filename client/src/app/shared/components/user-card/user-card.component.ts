import { Component, Input, Output, EventEmitter, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule, NgOptimizedImage } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../../core/services/api.service';
import { User } from '../../../models/user.model';

@Component({
    selector: 'app-user-card',
    imports: [CommonModule, NgOptimizedImage, RouterLink, MatButtonModule, MatIconModule],
    template: `
    <div class="user-card">
      <a [routerLink]="'/profile/' + user.username" class="user-info">
        <img [ngSrc]="user.avatar_url || 'assets/default-avatar.png'" width="40" height="40" class="avatar md" alt="" />
        <div>
          <div class="user-name">{{ user.full_name }}</div>
          <div class="user-meta">{{ user.friends_count }} mutual friends</div>
        </div>
      </a>
      <div class="user-actions">
        <button mat-stroked-button color="primary" (click)="sendRequest()" [disabled]="sent" class="small-btn">
          <mat-icon>{{ sent ? 'check' : 'person_add' }}</mat-icon>
          {{ sent ? 'Sent' : 'Add' }}
        </button>
        <button mat-icon-button (click)="dismiss()" title="Dismiss">
          <mat-icon>close</mat-icon>
        </button>
      </div>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    .user-card { display: flex; align-items: center; justify-content: space-between; padding: var(--space-2) 0; gap: var(--space-2); }
    .user-info { display: flex; align-items: center; gap: var(--space-2); min-width: 0; text-decoration: none; color: var(--text-primary); flex: 1; }
    .user-info:hover { color: var(--text-primary); }
    .user-info > div { min-width: 0; }
    .user-name { overflow: hidden; font-size: var(--font-size-sm); font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
    .user-meta { font-size: var(--font-size-xs); color: var(--text-muted); }
    .user-actions { display: flex; flex: none; align-items: center; gap: var(--space-1); }
    .small-btn { --mat-button-outlined-container-height: 32px; font-size: var(--font-size-xs); }
    @media (max-width: 600px) {
      .small-btn { --mat-button-outlined-container-height: 44px; }
      .user-actions { --mat-icon-button-state-layer-size: 44px; }
    }
  `]
})
export class UserCardComponent {
  @Input() user!: User;
  @Output() actionDone = new EventEmitter<void>();

  sent = false;

  constructor(private apiService: ApiService) {}

  sendRequest(): void {
    this.apiService.sendFriendRequest(this.user.id).subscribe(() => {
      this.sent = true;
    });
  }

  dismiss(): void {
    this.actionDone.emit();
  }
}
