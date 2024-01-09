import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../../core/services/api.service';
import { User } from '../../../models/user.model';

@Component({
  selector: 'app-user-card',
  standalone: true,
  imports: [CommonModule, RouterLink, MatButtonModule, MatIconModule],
  template: `
    <div class="user-card">
      <a [routerLink]="'/profile/' + user.username" class="user-info">
        <img [src]="user.avatar_url || 'assets/default-avatar.png'" class="avatar md" [alt]="user.username" />
        <div>
          <div class="font-semibold text-sm">{{ user.full_name }}</div>
          <div class="text-secondary" style="font-size:12px">{{ user.friends_count }} mutual friends</div>
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
  styles: [`
    .user-card { display: flex; align-items: center; justify-content: space-between; padding: 6px 0; gap: 8px; }
    .user-info { display: flex; align-items: center; gap: 8px; text-decoration: none; color: inherit; flex: 1; }
    .user-actions { display: flex; align-items: center; gap: 4px; }
    .small-btn { height: 30px; font-size: 12px; display: flex; align-items: center; gap: 4px; }
  `],
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
