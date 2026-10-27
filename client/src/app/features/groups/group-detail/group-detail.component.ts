import { Component, Input, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../../core/services/api.service';
import { Group, GroupMember } from '../../../models/group.model';

import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { CreatePostComponent } from '../../../shared/components/create-post/create-post.component';
import { PostCardComponent } from '../../../shared/components/post-card/post-card.component';
import { AuthService } from '../../../core/services/auth.service';
import { GroupJoinRequest } from '../../../models/group.model';
import { Post } from '../../../models/post.model';
import { User } from '../../../models/user.model';

@Component({
  selector: 'app-group-detail',
  standalone: true,
  imports: [
    CommonModule, RouterLink, MatButtonModule, MatIconModule, MatProgressSpinnerModule, MatSnackBarModule,
    CreatePostComponent, PostCardComponent,
  ],
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
            <button mat-flat-button color="primary" *ngIf="!group.is_member && !requested" (click)="join()">
              <mat-icon>group_add</mat-icon> {{ group.privacy === 'public' ? 'Join Group' : 'Request to Join' }}
            </button>
            <button mat-stroked-button disabled *ngIf="!group.is_member && requested">
              <mat-icon>schedule</mat-icon> Request Sent
            </button>
            <button mat-stroked-button color="warn" *ngIf="group.is_member" (click)="leave()">
              <mat-icon>logout</mat-icon> Leave Group
            </button>
          </div>
        </div>

        <!-- Pending join requests (admins and moderators) -->
        <div class="members-section" *ngIf="joinRequests.length > 0">
          <h3>Join requests ({{ joinRequests.length }})</h3>
          <div class="request-row" *ngFor="let jr of joinRequests">
            <a [routerLink]="'/profile/' + jr.user.username" class="member-card">
              <img [src]="jr.user.avatar_url || 'assets/default-avatar.png'" class="avatar md" [alt]="jr.user.username" />
              <span class="font-semibold text-sm">{{ jr.user.full_name }}</span>
            </a>
            <button mat-flat-button color="primary" (click)="decide(jr.id, 'approve')">Approve</button>
            <button mat-stroked-button (click)="decide(jr.id, 'decline')">Decline</button>
          </div>
        </div>

        <!-- Posts (members, or anyone for public groups) -->
        <div class="group-posts" *ngIf="canSeeContent">
          <app-create-post *ngIf="group.is_member" [currentUser]="currentUser" [groupId]="group.id"
            (postCreated)="posts.unshift($event)"></app-create-post>
          <app-post-card *ngFor="let p of posts" [post]="p" (postDeleted)="onPostDeleted($event)"></app-post-card>
          <p class="text-secondary" *ngIf="posts.length === 0">No posts yet.</p>
        </div>
        <p class="text-secondary private-note" *ngIf="!canSeeContent">
          <mat-icon>lock</mat-icon> Only members can see posts and members of this group.
        </p>

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
    .request-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
    .request-row .member-card { flex: 1; }
    .group-posts { margin-top: 24px; display: flex; flex-direction: column; gap: 16px; }
    .private-note { display: flex; align-items: center; gap: 6px; margin-top: 24px; }
    .loading-center { display: flex; justify-content: center; padding: 60px; }
  `]
})
export class GroupDetailComponent implements OnInit {
  @Input() id!: string;
  group: Group | null = null;
  members: GroupMember[] = [];
  loading = false;

  joinRequests: GroupJoinRequest[] = [];
  posts: Post[] = [];
  requested = false;
  currentUser: User | null = null;

  constructor(private apiService: ApiService, private authService: AuthService, private snackBar: MatSnackBar) {
    this.currentUser = this.authService.currentUser;
  }

  get canSeeContent(): boolean {
    return !!this.group && (this.group.privacy === 'public' || this.group.is_member);
  }

  get isModerator(): boolean {
    return this.group?.my_role === 'admin' || this.group?.my_role === 'moderator';
  }

  ngOnInit(): void {
    this.loading = true;
    const groupId = Number(this.id);
    this.apiService.getGroup(groupId).subscribe({
      next: (g) => {
        this.group = g;
        this.loading = false;
        if (this.canSeeContent) {
          this.loadMembers(groupId);
          this.loadPosts(groupId);
        }
        if (this.isModerator) this.loadJoinRequests(groupId);
      },
      error: () => (this.loading = false),
    });
  }

  loadMembers(groupId: number): void {
    this.apiService.getGroupMembers(groupId).subscribe({
      next: (members) => (this.members = members),
    });
  }

  loadPosts(groupId: number): void {
    this.apiService.getPosts({ group: String(groupId) }).subscribe({ next: (res) => (this.posts = res.results) });
  }

  loadJoinRequests(groupId: number): void {
    this.apiService.getGroupJoinRequests(groupId).subscribe({ next: (reqs) => (this.joinRequests = reqs) });
  }

  decide(requestId: number, decision: 'approve' | 'decline'): void {
    if (!this.group) return;
    const group = this.group;
    this.apiService.decideGroupJoinRequest(group.id, requestId, decision).subscribe({
      next: () => {
        this.joinRequests = this.joinRequests.filter((r) => r.id !== requestId);
        if (decision === 'approve') {
          group.members_count++;
          this.loadMembers(group.id);
        }
      },
      error: () => this.snackBar.open('Could not update the request', 'Dismiss', { duration: 3000 }),
    });
  }

  onPostDeleted(postId: number): void {
    this.posts = this.posts.filter((p) => p.id !== postId);
  }

  join(): void {
    if (!this.group) return;
    const group = this.group;
    this.apiService.joinGroup(group.id).subscribe({
      next: (res) => {
        if (res.status === 'request_pending') {
          this.requested = true;
          this.snackBar.open('Request sent to the group admins', 'Dismiss', { duration: 3000 });
          return;
        }
        group.is_member = true;
        group.my_role = 'member';
        group.members_count++;
        this.loadMembers(group.id);
        this.loadPosts(group.id);
      },
      error: (err) => this.snackBar.open(err?.error?.detail ?? 'Could not join', 'Dismiss', { duration: 3000 }),
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
