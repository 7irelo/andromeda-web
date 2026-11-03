import { Component, Input, Output, EventEmitter, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule, NgOptimizedImage } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../../core/services/api.service';
import { User } from '../../../models/user.model';

@Component({
    selector: 'app-user-card',
    imports: [CommonModule, NgOptimizedImage, RouterLink, MatIconModule],
    template: `
    <div class="user-card">
      <a [routerLink]="'/profile/' + user.username" class="user-info">
        <img [ngSrc]="user.avatar_url || 'assets/default-avatar.png'" width="32" height="32" class="avatar sm" alt="" />
        <span class="names">
          <span class="name">{{ user.full_name }}</span>
          <span class="handle">&#64;{{ user.username }}</span>
        </span>
      </a>
      <button type="button" class="add-btn" (click)="sendRequest()" [disabled]="sent">
        <span *ngIf="sent; else addLabel" i18n="@@userCard.sent">Sent</span>
        <ng-template #addLabel><span i18n="@@userCard.add">Add</span></ng-template>
      </button>
      <button type="button" class="dismiss-btn" (click)="dismiss()" title="Dismiss" aria-label="Dismiss"
              i18n-title="@@userCard.dismiss" i18n-aria-label="@@userCard.dismiss">
        <mat-icon aria-hidden="true">close</mat-icon>
      </button>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    .user-card { display: flex; align-items: center; gap: 6px; padding: 6px 0; }
    .user-info {
      flex: 1; min-width: 0; display: flex; align-items: center; gap: 8px; color: inherit;
      &:hover { color: inherit; text-decoration: none; .name { text-decoration: underline; } }
    }
    .names { min-width: 0; display: flex; flex-direction: column; }
    .name, .handle { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .name { font-size: 13px; font-weight: 600; line-height: 18px; color: var(--text-primary); }
    .handle { font-size: 12px; line-height: 16px; color: var(--text-muted); }
    .add-btn {
      flex-shrink: 0; height: 30px; padding: 0 4px; border: none; background: none; font: inherit;
      font-size: 13px; font-weight: 600; color: var(--primary); cursor: pointer;
      &:hover:not(:disabled) { color: var(--text-primary); }
      &:disabled { color: var(--text-muted); cursor: default; }
      &:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
    }
    .dismiss-btn {
      flex-shrink: 0; display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 30px; padding: 0;
      border: none; border-radius: var(--radius-sm); background: none; color: var(--text-muted); cursor: pointer;
      mat-icon { font-size: 16px; width: 16px; height: 16px; }
      &:hover { background: var(--surface-2); color: var(--text-primary); }
      &:focus-visible { outline: 2px solid var(--primary); outline-offset: -2px; }
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
