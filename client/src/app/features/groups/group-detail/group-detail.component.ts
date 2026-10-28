import { Component, Input, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatTabsModule } from '@angular/material/tabs';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../../core/services/api.service';
import { AuthService } from '../../../core/services/auth.service';
import { CreatePostComponent } from '../../../shared/components/create-post/create-post.component';
import { PostCardComponent } from '../../../shared/components/post-card/post-card.component';
import { Group, GroupJoinRequest, GroupMember, GroupRole, GroupRule } from '../../../models/group.model';
import { Post } from '../../../models/post.model';
import { User } from '../../../models/user.model';
import { GroupManageComponent } from '../group-manage/group-manage.component';

const MAX_PINS = 3;

@Component({
    selector: 'app-group-detail',
    imports: [
        CommonModule, RouterLink, MatButtonModule, MatIconModule, MatMenuModule, MatTabsModule,
        MatProgressSpinnerModule, MatSnackBarModule,
        CreatePostComponent, PostCardComponent, GroupManageComponent,
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

      <div class="group-actions">
        <ng-container *ngIf="!group.is_member">
          <button mat-stroked-button disabled *ngIf="group.is_banned">
            <mat-icon>block</mat-icon> You can't join this group
          </button>
          <ng-container *ngIf="!group.is_banned && group.privacy !== 'secret'">
            <button mat-flat-button color="primary" *ngIf="!requested" (click)="startJoin()">
              <mat-icon>group_add</mat-icon> {{ group.privacy === 'public' ? 'Join Group' : 'Request to Join' }}
            </button>
            <button mat-stroked-button disabled *ngIf="requested">
              <mat-icon>schedule</mat-icon> Request Sent
            </button>
          </ng-container>
        </ng-container>
        <button mat-stroked-button color="warn" *ngIf="group.is_member" (click)="leave()">
          <mat-icon>logout</mat-icon> Leave Group
        </button>
      </div>

      <!-- Rules shown before joining -->
      <div class="card rules-prompt" *ngIf="showRulesPrompt">
        <h3>Before you join: group rules</h3>
        <ol class="rules-list">
          <li *ngFor="let r of rules"><strong>{{ r.title }}</strong><p *ngIf="r.description">{{ r.description }}</p></li>
        </ol>
        <div class="row-actions">
          <button mat-stroked-button (click)="showRulesPrompt = false">Cancel</button>
          <button mat-flat-button color="primary" (click)="join()">I agree, join</button>
        </div>
      </div>

      <mat-tab-group animationDuration="0ms">
        <mat-tab label="Posts">
          <div class="tab-body">
            <!-- Pending join requests (admins and moderators) -->
            <div class="card section" *ngIf="isModerator && joinRequests.length > 0">
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

            <div class="group-posts" *ngIf="canSeeContent">
              <app-create-post *ngIf="group.is_member" [currentUser]="currentUser" [groupId]="group.id"
                (postCreated)="posts.unshift($event)"></app-create-post>

              <div *ngFor="let p of pinned" class="pinned-post">
                <div class="post-toolbar">
                  <span class="pin-label"><mat-icon>push_pin</mat-icon> Pinned</span>
                  <ng-container *ngTemplateOutlet="modMenu; context: { $implicit: p, pinned: true }"></ng-container>
                </div>
                <app-post-card [post]="p" (postDeleted)="onPostDeleted($event)"></app-post-card>
              </div>

              <div *ngFor="let p of posts">
                <div class="post-toolbar" *ngIf="isModerator">
                  <span></span>
                  <ng-container *ngTemplateOutlet="modMenu; context: { $implicit: p, pinned: false }"></ng-container>
                </div>
                <app-post-card [post]="p" (postDeleted)="onPostDeleted($event)"></app-post-card>
              </div>
              <p class="text-secondary" *ngIf="posts.length === 0 && pinned.length === 0">No posts yet.</p>
            </div>
            <p class="text-secondary private-note" *ngIf="!canSeeContent">
              <mat-icon>lock</mat-icon> Only members can see posts and members of this group.
            </p>
          </div>
        </mat-tab>

        <mat-tab label="About">
          <div class="tab-body">
            <div class="card section">
              <h3>About</h3>
              <p class="text-secondary">{{ group.description || 'No description yet.' }}</p>
              <p class="text-secondary text-sm privacy-line">
                <mat-icon>{{ privacyIcon }}</mat-icon> {{ privacyText }}
              </p>
            </div>
            <div class="card section">
              <h3>Rules</h3>
              <ol class="rules-list" *ngIf="rules.length > 0">
                <li *ngFor="let r of rules"><strong>{{ r.title }}</strong><p *ngIf="r.description">{{ r.description }}</p></li>
              </ol>
              <p class="text-secondary" *ngIf="rules.length === 0">This group has no rules yet.</p>
            </div>
          </div>
        </mat-tab>

        <mat-tab label="Members" *ngIf="canSeeContent">
          <div class="tab-body">
            <div class="members-grid">
              <div *ngFor="let m of members" class="member-card">
                <a [routerLink]="'/profile/' + m.user.username" class="member-link">
                  <img [src]="m.user.avatar_url || 'assets/default-avatar.png'" class="avatar md" [alt]="m.user.username" />
                  <div class="member-info">
                    <span class="font-semibold text-sm">{{ m.user.full_name }}</span>
                    <span class="text-xs text-secondary" *ngIf="m.role !== 'member'">{{ m.role | titlecase }}</span>
                  </div>
                </a>
                <button mat-icon-button *ngIf="canManage(m)" [matMenuTriggerFor]="memberMenu" aria-label="Member actions">
                  <mat-icon>more_vert</mat-icon>
                </button>
                <mat-menu #memberMenu="matMenu">
                  <ng-container *ngIf="isAdmin">
                    <button mat-menu-item *ngIf="m.role !== 'admin'" (click)="setRole(m, 'admin')">Make admin</button>
                    <button mat-menu-item *ngIf="m.role !== 'moderator'" (click)="setRole(m, 'moderator')">Make moderator</button>
                    <button mat-menu-item *ngIf="m.role !== 'member'" (click)="setRole(m, 'member')">Make member</button>
                  </ng-container>
                  <button mat-menu-item *ngIf="m.role === 'member' || isAdmin" (click)="kick(m)">Remove from group</button>
                  <button mat-menu-item *ngIf="isAdmin && m.role !== 'admin'" (click)="ban(m)">Ban from group</button>
                </mat-menu>
              </div>
            </div>
          </div>
        </mat-tab>

        <mat-tab label="Manage" *ngIf="isModerator">
          <div class="tab-body">
            <app-group-manage [group]="group" [isAdmin]="isAdmin"
              (groupChange)="onGroupChange($event)" (rulesChange)="rules = $event"
              (deleted)="onDeleted()"></app-group-manage>
          </div>
        </mat-tab>
      </mat-tab-group>
    </div>

    <ng-template #modMenu let-p let-isPinned="pinned">
      <ng-container *ngIf="isModerator">
        <button mat-icon-button [matMenuTriggerFor]="postMenu" aria-label="Moderate post">
          <mat-icon>more_horiz</mat-icon>
        </button>
        <mat-menu #postMenu="matMenu">
          <button mat-menu-item *ngIf="!isPinned" [disabled]="pinned.length >= maxPins" (click)="pin(p, true)">
            <mat-icon>push_pin</mat-icon> Pin to top
          </button>
          <button mat-menu-item *ngIf="isPinned" (click)="pin(p, false)"><mat-icon>push_pin</mat-icon> Unpin</button>
          <button mat-menu-item (click)="removePost(p)"><mat-icon>delete</mat-icon> Remove post</button>
        </mat-menu>
      </ng-container>
    </ng-template>

    <div class="loading-center" *ngIf="loading">
      <mat-spinner diameter="40"></mat-spinner>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    .group-detail { max-width: 800px; margin: 0 auto; padding: 16px; }
    .group-cover {
      position: relative; height: 240px; border-radius: 16px; overflow: hidden; margin-bottom: 16px;
    }
    .group-cover img { width: 100%; height: 100%; object-fit: cover; }
    .cover-overlay {
      position: absolute; bottom: 0; left: 0; right: 0;
      background: linear-gradient(transparent, rgba(0,0,0,.7));
      color: #fff; padding: 24px;
    }
    .cover-overlay h1 { font-size: 28px; font-weight: 800; }
    .cover-overlay p { opacity: .9; margin-top: 4px; }
    .group-actions { display: flex; justify-content: flex-end; gap: 8px; margin-bottom: 12px; }
    .tab-body { display: flex; flex-direction: column; gap: 16px; padding: 16px 0; }
    .section { padding: 16px 20px; }
    .section h3, .rules-prompt h3 { font-size: 16px; font-weight: 700; margin-bottom: 8px; }
    .rules-prompt { padding: 16px 20px; margin-bottom: 12px; }
    .rules-list { padding-left: 20px; display: flex; flex-direction: column; gap: 8px; }
    .rules-list p { color: var(--text-secondary); margin-top: 2px; }
    .row-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
    .privacy-line { display: flex; align-items: center; gap: 6px; margin-top: 12px; }
    .members-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
    .member-card {
      display: flex; align-items: center; gap: 4px; padding: 8px 4px 8px 12px;
      background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
      text-decoration: none; color: inherit;
    }
    .member-link { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; text-decoration: none; color: inherit; }
    .member-info { display: flex; flex-direction: column; min-width: 0; }
    .request-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
    .request-row .member-card { flex: 1; }
    .group-posts { display: flex; flex-direction: column; gap: 16px; }
    .post-toolbar { display: flex; align-items: center; justify-content: space-between; min-height: 32px; }
    .pin-label { display: flex; align-items: center; gap: 4px; font-size: 13px; font-weight: 600; color: var(--primary); }
    .pin-label mat-icon { font-size: 18px; width: 18px; height: 18px; }
    .private-note { display: flex; align-items: center; gap: 6px; }
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
  pinned: Post[] = [];
  rules: GroupRule[] = [];
  requested = false;
  showRulesPrompt = false;
  currentUser: User | null = null;
  readonly maxPins = MAX_PINS;

  constructor(
    private apiService: ApiService,
    private authService: AuthService,
    private snackBar: MatSnackBar,
    private router: Router,
  ) {
    this.currentUser = this.authService.currentUser;
  }

  get canSeeContent(): boolean {
    return !!this.group && (this.group.privacy === 'public' || this.group.is_member);
  }

  get isAdmin(): boolean {
    return this.group?.my_role === 'admin';
  }

  get isModerator(): boolean {
    return this.group?.my_role === 'admin' || this.group?.my_role === 'moderator';
  }

  get privacyIcon(): string {
    return { public: 'public', private: 'lock', secret: 'visibility_off' }[this.group?.privacy ?? 'public'];
  }

  get privacyText(): string {
    return {
      public: 'Public: anyone can see who is in the group and what they post.',
      private: 'Private: anyone can find the group, but only members see posts and members.',
      secret: 'Secret: only members and people with an invite link can find this group.',
    }[this.group?.privacy ?? 'public'];
  }

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading = true;
    const groupId = Number(this.id);
    this.apiService.getGroup(groupId).subscribe({
      next: (g) => {
        this.group = g;
        this.requested = !!g.has_requested;
        this.loading = false;
        this.apiService.getGroupRules(groupId).subscribe({ next: (rules) => (this.rules = rules) });
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
    this.apiService.getGroupPinnedPosts(groupId).subscribe({
      next: (pinned) => {
        this.pinned = pinned;
        this.apiService.getPosts({ group: String(groupId) }).subscribe({
          next: (res) => {
            // Pinned posts are already shown at the top.
            const pinnedIds = new Set(pinned.map((p) => p.id));
            this.posts = res.results.filter((p) => !pinnedIds.has(p.id));
          },
        });
      },
    });
  }

  loadJoinRequests(groupId: number): void {
    this.apiService.getGroupJoinRequests(groupId).subscribe({ next: (reqs) => (this.joinRequests = reqs) });
  }

  canManage(m: GroupMember): boolean {
    if (!this.isModerator || m.user.id === this.currentUser?.id) return false;
    return this.isAdmin || m.role === 'member';
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
      error: (err) => this.toast(err?.error?.detail ?? 'Could not update the request'),
    });
  }

  onPostDeleted(postId: number): void {
    this.posts = this.posts.filter((p) => p.id !== postId);
    this.pinned = this.pinned.filter((p) => p.id !== postId);
  }

  startJoin(): void {
    if (this.rules.length > 0) {
      this.showRulesPrompt = true;
      return;
    }
    this.join();
  }

  join(): void {
    if (!this.group) return;
    const group = this.group;
    this.showRulesPrompt = false;
    this.apiService.joinGroup(group.id).subscribe({
      next: (res) => {
        if (res.status === 'request_pending') {
          this.requested = true;
          this.toast('Request sent to the group admins');
          return;
        }
        group.is_member = true;
        group.my_role = 'member';
        group.members_count++;
        this.loadMembers(group.id);
        this.loadPosts(group.id);
      },
      error: (err) => this.toast(err?.error?.detail ?? 'Could not join'),
    });
  }

  leave(): void {
    if (!this.group) return;
    const group = this.group;
    this.apiService.leaveGroup(group.id).subscribe({
      next: () => {
        group.is_member = false;
        group.my_role = null;
        group.members_count--;
        if (!this.canSeeContent) {
          this.posts = [];
          this.pinned = [];
          this.members = [];
        }
      },
      error: (err) => this.toast(err?.error?.detail ?? 'Could not leave the group'),
    });
  }

  setRole(m: GroupMember, role: GroupRole): void {
    if (!this.group) return;
    this.apiService.setGroupRole(this.group.id, m.user.id, role).subscribe({
      next: () => (m.role = role),
      error: (err) => this.toast(err?.error?.detail ?? 'Could not change the role'),
    });
  }

  kick(m: GroupMember): void {
    if (!this.group || !confirm(`Remove ${m.user.full_name} from the group? They can join again later.`)) return;
    const group = this.group;
    this.apiService.removeGroupMember(group.id, m.user.id).subscribe({
      next: () => {
        this.members = this.members.filter((x) => x.id !== m.id);
        group.members_count--;
      },
      error: (err) => this.toast(err?.error?.detail ?? 'Could not remove this member'),
    });
  }

  ban(m: GroupMember): void {
    if (!this.group) return;
    const reason = prompt(`Ban ${m.user.full_name}? They won't be able to rejoin. Reason (optional):`);
    if (reason === null) return;
    const group = this.group;
    this.apiService.banGroupMember(group.id, m.user.id, reason).subscribe({
      next: () => {
        this.members = this.members.filter((x) => x.id !== m.id);
        group.members_count--;
        // Their posts in the group are hidden by the server once banned.
        this.loadPosts(group.id);
        this.toast(`${m.user.full_name} was banned`);
      },
      error: (err) => this.toast(err?.error?.detail ?? 'Could not ban this member'),
    });
  }

  pin(p: Post, pin: boolean): void {
    if (!this.group) return;
    const group = this.group;
    this.apiService.pinGroupPost(group.id, p.id, pin).subscribe({
      next: () => this.loadPosts(group.id),
      error: (err) => this.toast(err?.error?.detail ?? 'Could not update the pin'),
    });
  }

  removePost(p: Post): void {
    if (!this.group || !confirm('Remove this post from the group?')) return;
    this.apiService.removeGroupPost(this.group.id, p.id).subscribe({
      next: () => this.onPostDeleted(p.id),
      error: (err) => this.toast(err?.error?.detail ?? 'Could not remove the post'),
    });
  }

  onGroupChange(updated: Group): void {
    this.group = { ...this.group, ...updated };
  }

  onDeleted(): void {
    this.router.navigate(['/groups']);
  }

  private toast(message: string): void {
    this.snackBar.open(message, 'Dismiss', { duration: 3000 });
  }
}
