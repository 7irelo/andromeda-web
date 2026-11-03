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
import { EmptyStateComponent, ErrorStateComponent, SkeletonComponent } from '../../../shared/components/states';

const MAX_PINS = 3;

@Component({
    selector: 'app-group-detail',
    imports: [
        CommonModule, RouterLink, MatButtonModule, MatIconModule, MatMenuModule, MatTabsModule,
        MatProgressSpinnerModule, MatSnackBarModule,
        CreatePostComponent, PostCardComponent, GroupManageComponent,
        EmptyStateComponent, ErrorStateComponent, SkeletonComponent,
    ],
    template: `
    <div class="page ui-controls" *ngIf="group">
      <header class="entity">
        <div class="entity-cover">
          <img *ngIf="group.cover_photo" [src]="group.cover_photo" alt="" />
        </div>
        <div class="entity-body">
          <div class="entity-main">
            <div class="entity-head">
              <div class="entity-title">
                <h1>{{ group.name }}</h1>
                <p i18n="@@groups.privacyLine">{{ group.privacy | titlecase }} group</p>
              </div>
              <div class="entity-actions">
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
                <button mat-stroked-button class="btn-danger" *ngIf="group.is_member" (click)="leave()">
                  <mat-icon>logout</mat-icon> Leave Group
                </button>
              </div>
            </div>
            <div class="entity-foot">
              <div class="entity-about">
                <p *ngIf="group.description">{{ group.description }}</p>
              </div>
              <dl class="entity-stats">
                <div>
                  <dt>Members</dt>
                  <dd>{{ group.members_count | number }}</dd>
                </div>
              </dl>
            </div>
          </div>
        </div>

        <!-- Rules shown before joining -->
        <div class="entity-notice section" *ngIf="showRulesPrompt">
          <h3>Before you join: group rules</h3>
          <ol class="rules-list">
            <li *ngFor="let r of rules"><strong>{{ r.title }}</strong><p *ngIf="r.description">{{ r.description }}</p></li>
          </ol>
          <div class="row-actions">
            <button mat-stroked-button (click)="showRulesPrompt = false">Cancel</button>
            <button mat-flat-button color="primary" (click)="join()">I agree, join</button>
          </div>
        </div>
      </header>

      <mat-tab-group class="entity-tabs" mat-stretch-tabs="false" animationDuration="0ms">
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

            <div class="feed-col" *ngIf="canSeeContent">
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
              <app-skeleton *ngIf="postsLoading" variant="post" [count]="2"></app-skeleton>
              <app-error-state *ngIf="!postsLoading && postsError" [compact]="true"
                               (retry)="loadPosts(group.id)"></app-error-state>
              <app-empty-state *ngIf="!postsLoading && !postsError && posts.length === 0 && pinned.length === 0"
                               icon="forum" title="No posts yet" [compact]="true"
                               [message]="group.is_member ? 'Start the conversation with the first post.' : ''"></app-empty-state>
            </div>
            <p class="muted-note private-note" *ngIf="!canSeeContent">
              <mat-icon>lock</mat-icon> Only members can see posts and members of this group.
            </p>
          </div>
        </mat-tab>

        <mat-tab label="About">
          <div class="tab-body">
            <div class="card section">
              <h3>About</h3>
              <p>{{ group.description || 'No description yet.' }}</p>
              <ul class="info-list">
                <li><mat-icon>{{ privacyIcon }}</mat-icon> {{ privacyText }}</li>
              </ul>
            </div>
            <div class="card section">
              <h3>Rules</h3>
              <ol class="rules-list" *ngIf="rules.length > 0">
                <li *ngFor="let r of rules"><strong>{{ r.title }}</strong><p *ngIf="r.description">{{ r.description }}</p></li>
              </ol>
              <p *ngIf="rules.length === 0">This group has no rules yet.</p>
            </div>
          </div>
        </mat-tab>

        <mat-tab label="Members" *ngIf="canSeeContent">
          <div class="tab-body">
            <div class="member-grid">
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

    <div class="page" *ngIf="loading">
      <app-skeleton variant="card" [count]="1"></app-skeleton>
      <app-skeleton variant="post" [count]="2"></app-skeleton>
    </div>
    <div class="page" *ngIf="!loading && loadError">
      <app-error-state [title]="loadError === 404 ? 'Group not found' : ''"
                       [message]="loadError === 404 ? 'It may have been deleted, or it is a secret group you are not in.' : ''"
                       (retry)="load()"></app-error-state>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styleUrls: ['../../../shared/styles/ui-controls.scss', '../../../shared/styles/entity.scss', '../../../shared/styles/ui-cards.scss'],
    styles: [`
    .rules-list { display: flex; flex-direction: column; gap: var(--space-2); margin: 0; padding-left: var(--space-5); font-size: 13px; }
    .rules-list p { margin: 2px 0 0; color: var(--text-secondary); }
    .row-actions { display: flex; justify-content: flex-end; flex-wrap: wrap; gap: var(--space-2); margin-top: var(--space-3); }
    .member-link { display: flex; align-items: center; gap: var(--space-3); flex: 1; min-width: 0; min-height: var(--touch-target); color: inherit; }
    .member-link:hover { text-decoration: none; }
    .member-info { display: flex; flex-direction: column; min-width: 0; overflow-wrap: anywhere; }
    .request-row { display: flex; align-items: center; flex-wrap: wrap; gap: var(--space-2); margin-bottom: var(--space-2); }
    .request-row .member-card { flex: 1 1 200px; }
    .post-toolbar { display: flex; align-items: center; justify-content: space-between; min-height: 36px; }
    .pin-label { display: flex; align-items: center; gap: var(--space-1); font-size: 13px; font-weight: 500; color: var(--text-secondary); }
    .pin-label mat-icon { width: 16px; height: 16px; font-size: 16px; }
    .private-note { display: flex; align-items: center; gap: var(--space-2); }
  `]
})
export class GroupDetailComponent implements OnInit {
  @Input() id!: string;
  group: Group | null = null;
  members: GroupMember[] = [];
  loading = false;
  /** 0 when fine; otherwise the HTTP status (or -1) of the failed load. */
  loadError = 0;
  postsLoading = false;
  postsError = false;

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
    this.loadError = 0;
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
      error: (err) => {
        this.loading = false;
        this.loadError = err?.status || -1;
      },
    });
  }

  loadMembers(groupId: number): void {
    this.apiService.getGroupMembers(groupId).subscribe({
      next: (members) => (this.members = members),
    });
  }

  loadPosts(groupId: number): void {
    this.postsLoading = true;
    this.postsError = false;
    const failed = () => {
      this.postsLoading = false;
      this.postsError = true;
    };
    this.apiService.getGroupPinnedPosts(groupId).subscribe({
      next: (pinned) => {
        this.pinned = pinned;
        this.apiService.getPosts({ group: String(groupId) }).subscribe({
          next: (res) => {
            // Pinned posts are already shown at the top.
            const pinnedIds = new Set(pinned.map((p) => p.id));
            this.posts = res.results.filter((p) => !pinnedIds.has(p.id));
            this.postsLoading = false;
          },
          error: failed,
        });
      },
      error: failed,
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
