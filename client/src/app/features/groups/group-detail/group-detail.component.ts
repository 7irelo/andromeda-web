import { Component, Input, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../../core/services/api.service';
import { Group, GroupMember } from '../../../models/group.model';

@Component({
  selector: 'app-group-detail',
  standalone: true,
  imports: [CommonModule, RouterLink, MatButtonModule, MatIconModule, MatProgressSpinnerModule],
  template: `
    <div class="group-detail" *ngIf="group">
      <div class="group-cover">
        <img [src]="group.cover_photo || 'assets/default-cover.png'" alt="" />
        <div class="cover-overlay">
          <h1>{{ group.name }}</h1>
          <p>{{ group.members_count | number }} members · {{ group.privacy | titlecase }}</p>
        </div>
      </div>

      <div class="group-body">
        <div class="group-info-row">
          <div class="group-description" *ngIf="group.description">
            <h3>About</h3>
            <p>{{ group.description }}</p>
          </div>
          <div class="group-actions">
            <button mat-flat-button color="primary" *ngIf="!group.is_member" (click)="join()">
              <mat-icon>group_add</mat-icon> Join Group
            </button>
            <button mat-stroked-button color="warn" *ngIf="group.is_member" (click)="leave()">
              <mat-icon>logout</mat-icon> Leave Group
            </button>
          </div>
        </div>

        <!-- Members -->
        <div class="members-section" *ngIf="members.length > 0">
          <h3>Members ({{ group.members_count }})</h3>
          <div class="members-grid">
            <a
              *ngFor="let m of members"
              [routerLink]="'/profile/' + m.user.username"
              class="member-card"
            >
              <img [src]="m.user.avatar_url || 'assets/default-avatar.png'" class="avatar md" [alt]="m.user.username" />
              <div class="member-info">
                <span class="font-semibold text-sm">{{ m.user.full_name }}</span>
                <span class="text-xs text-secondary" *ngIf="m.role !== 'member'">{{ m.role | titlecase }}</span>
              </div>
            </a>
          </div>
        </div>
      </div>
    </div>

    <div class="loading-center" *ngIf="loading">
      <mat-spinner diameter="40"></mat-spinner>
    </div>
  `,
  styles: [`
    .group-detail { max-width: 800px; margin: 0 auto; padding: 16px; }
    .group-cover {
      position: relative; height: 240px; border-radius: 16px; overflow: hidden; margin-bottom: 20px;
    }
    .group-cover img { width: 100%; height: 100%; object-fit: cover; }
    .cover-overlay {
      position: absolute; bottom: 0; left: 0; right: 0;
      background: linear-gradient(transparent, rgba(0,0,0,.7));
      color: #fff; padding: 24px;
    }
    .cover-overlay h1 { font-size: 28px; font-weight: 800; }
    .cover-overlay p { opacity: .9; margin-top: 4px; }
    .group-body { display: flex; flex-direction: column; gap: 24px; }
    .group-info-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
    .group-description { flex: 1; }
    .group-description h3 { font-size: 16px; font-weight: 700; margin-bottom: 8px; }
    .group-description p { color: var(--text-secondary); line-height: 1.6; }
    .members-section h3 { font-size: 16px; font-weight: 700; margin-bottom: 12px; }
    .members-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
    .member-card {
      display: flex; align-items: center; gap: 10px; padding: 10px 12px;
      background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
      text-decoration: none; color: inherit; transition: box-shadow .2s;
    }
    .member-card:hover { box-shadow: var(--shadow-md); text-decoration: none; }
    .member-info { display: flex; flex-direction: column; }
    .loading-center { display: flex; justify-content: center; padding: 60px; }
  `]
})
export class GroupDetailComponent implements OnInit {
  @Input() id!: string;
  group: Group | null = null;
  members: GroupMember[] = [];
  loading = false;

  constructor(private apiService: ApiService) {}

  ngOnInit(): void {
    this.loading = true;
    const groupId = Number(this.id);
    this.apiService.getGroup(groupId).subscribe({
      next: (g) => {
        this.group = g;
        this.loading = false;
        this.loadMembers(groupId);
      },
      error: () => (this.loading = false),
    });
  }

  loadMembers(groupId: number): void {
    this.apiService.getGroupMembers(groupId).subscribe({
      next: (members) => (this.members = members),
    });
  }

  join(): void {
    if (!this.group) return;
    this.apiService.joinGroup(this.group.id).subscribe(() => {
      if (this.group) {
        this.group.is_member = true;
        this.group.members_count++;
      }
    });
  }

  leave(): void {
    if (!this.group) return;
    this.apiService.leaveGroup(this.group.id).subscribe(() => {
      if (this.group) {
        this.group.is_member = false;
        this.group.members_count--;
      }
    });
  }
}
