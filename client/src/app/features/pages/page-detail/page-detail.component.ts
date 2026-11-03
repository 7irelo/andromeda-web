import { Component, Input, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../../core/services/api.service';
import { PostCardComponent } from '../../../shared/components/post-card/post-card.component';
import { Page, PAGE_CATEGORIES } from '../../../models/page.model';
import { Post } from '../../../models/post.model';
import { User } from '../../../models/user.model';
import { PageManageComponent } from '../page-manage/page-manage.component';

/** `/pages/:id`: posts, about and followers tabs, plus a manage tab for the page team. */
@Component({
    selector: 'app-page-detail',
    imports: [
        CommonModule, RouterLink, MatButtonModule, MatIconModule, MatProgressSpinnerModule, MatTabsModule,
        MatTooltipModule, MatSnackBarModule, PostCardComponent, PageManageComponent,
    ],
    template: `
    <div class="page ui-controls" *ngIf="page">
      <header class="entity">
        <div class="entity-cover">
          <img *ngIf="page.cover_photo" [src]="page.cover_photo" alt="" />
        </div>
        <div class="entity-body">
          <div class="entity-avatar square">
            <img [src]="page.avatar || 'assets/default-avatar.png'" [alt]="page.name" />
          </div>
          <div class="entity-main">
            <div class="entity-head">
              <div class="entity-title">
                <h1>
                  {{ page.name }}
                  <mat-icon class="verified" *ngIf="page.is_verified" matTooltip="Verified page" aria-label="Verified">verified</mat-icon>
                </h1>
                <p>&#64;{{ page.username }} · {{ categoryLabel }}</p>
              </div>
              <div class="entity-actions">
                <button mat-flat-button color="primary" *ngIf="!page.is_following" (click)="follow()">
                  <mat-icon>add</mat-icon> Follow
                </button>
                <button mat-stroked-button *ngIf="page.is_following" (click)="unfollow()">
                  <mat-icon>check</mat-icon> Following
                </button>
              </div>
            </div>
            <div class="entity-foot">
              <div class="entity-about">
                <p *ngIf="page.description">{{ page.description }}</p>
              </div>
              <dl class="entity-stats">
                <div>
                  <dt>Followers</dt>
                  <dd>{{ page.followers_count | number }}</dd>
                </div>
              </dl>
            </div>
          </div>
        </div>
      </header>

      <mat-tab-group class="entity-tabs" mat-stretch-tabs="false" animationDuration="0ms" (selectedIndexChange)="onTab($event)">
        <mat-tab label="Posts">
          <div class="tab-body">
            <div class="feed-col">
              <app-post-card *ngFor="let p of posts" [post]="p" (postDeleted)="onPostDeleted($event)"></app-post-card>
              <p class="muted-note" *ngIf="postsLoaded && posts.length === 0">No posts yet.</p>
              <button mat-stroked-button class="load-more" *ngIf="postsNext" (click)="loadPosts(postsPage + 1)">Load more</button>
            </div>
          </div>
        </mat-tab>

        <mat-tab label="About">
          <div class="tab-body">
            <div class="card section">
              <h3>About</h3>
              <p>{{ page.description || 'No description yet.' }}</p>
              <ul class="info-list">
                <li *ngIf="page.website">
                  <mat-icon>language</mat-icon>
                  <a [href]="safeWebsite" target="_blank" rel="noopener noreferrer nofollow">{{ page.website }}</a>
                </li>
                <li *ngIf="page.email"><mat-icon>mail</mat-icon> <a [href]="'mailto:' + page.email">{{ page.email }}</a></li>
                <li *ngIf="page.phone"><mat-icon>call</mat-icon> {{ page.phone }}</li>
                <li><mat-icon>event</mat-icon> Created {{ page.created_at | date }}</li>
              </ul>
            </div>
          </div>
        </mat-tab>

        <mat-tab label="Followers">
          <div class="tab-body">
            <div class="member-grid">
              <a *ngFor="let u of followers" class="member-card" [routerLink]="'/profile/' + u.username">
                <img [src]="u.avatar_url || 'assets/default-avatar.png'" class="avatar md" [alt]="u.username" />
                <span class="font-semibold text-sm">{{ u.full_name }}</span>
              </a>
            </div>
            <p class="muted-note" *ngIf="followersLoaded && followers.length === 0">No followers yet.</p>
            <button mat-stroked-button class="load-more" *ngIf="followersNext" (click)="loadFollowers(followersPage + 1)">Load more</button>
          </div>
        </mat-tab>

        <mat-tab label="Manage" *ngIf="page.my_role">
          <div class="tab-body">
            <app-page-manage [page]="page" (pageChange)="onPageChange($event)" (deleted)="onDeleted()"></app-page-manage>
          </div>
        </mat-tab>
      </mat-tab-group>
    </div>

    <div class="state-center" *ngIf="loading"><mat-spinner diameter="40"></mat-spinner></div>
    <div class="empty-state ui-controls" *ngIf="notFound">
      <mat-icon aria-hidden="true">auto_stories</mat-icon>
      <p>This page doesn't exist.</p>
      <a mat-stroked-button routerLink="/pages">Browse pages</a>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styleUrls: ['../../../shared/styles/ui-controls.scss', '../../../shared/styles/entity.scss', '../../../shared/styles/ui-cards.scss'],
    styles: [`
    .load-more { align-self: center; }
    .member-card { min-height: 56px; }
    .empty-state { display: flex; flex-direction: column; align-items: center; gap: var(--space-3); padding: var(--space-12) var(--space-4); font-size: 14px; color: var(--text-secondary); }
    .empty-state p { margin: 0; }
    .empty-state mat-icon { width: 32px; height: 32px; font-size: 32px; color: var(--text-muted); }
  `]
})
export class PageDetailComponent implements OnInit {
  @Input() id!: string;
  page: Page | null = null;
  loading = false;
  notFound = false;

  posts: Post[] = [];
  postsPage = 1;
  postsNext = false;
  postsLoaded = false;

  followers: User[] = [];
  followersPage = 1;
  followersNext = false;
  followersLoaded = false;

  constructor(private apiService: ApiService, private snackBar: MatSnackBar, private router: Router) {}

  get categoryLabel(): string {
    return PAGE_CATEGORIES.find((c) => c.value === this.page?.category)?.label ?? 'Other';
  }

  /** The server validates URLs, but only ever link out to http(s). */
  get safeWebsite(): string | null {
    const url = this.page?.website ?? '';
    return /^https?:\/\//i.test(url) ? url : null;
  }

  ngOnInit(): void {
    if (!/^\d+$/.test(this.id ?? '')) {
      this.notFound = true;
      return;
    }
    this.loading = true;
    this.apiService.getPage(Number(this.id)).subscribe({
      next: (p) => {
        this.page = p;
        this.loading = false;
        this.loadPosts(1);
      },
      error: () => {
        this.loading = false;
        this.notFound = true;
      },
    });
  }

  onTab(index: number): void {
    if (index === 2 && !this.followersLoaded) this.loadFollowers(1);
  }

  loadPosts(page: number): void {
    if (!this.page) return;
    this.apiService.getPagePosts(this.page.id, page).subscribe({
      next: (res) => {
        this.posts = page === 1 ? res.results : [...this.posts, ...res.results];
        this.postsPage = page;
        this.postsNext = !!res.next;
        this.postsLoaded = true;
      },
    });
  }

  loadFollowers(page: number): void {
    if (!this.page) return;
    this.apiService.getPageFollowers(this.page.id, page).subscribe({
      next: (res) => {
        this.followers = page === 1 ? res.results : [...this.followers, ...res.results];
        this.followersPage = page;
        this.followersNext = !!res.next;
        this.followersLoaded = true;
      },
    });
  }

  onPostDeleted(postId: number): void {
    this.posts = this.posts.filter((p) => p.id !== postId);
  }

  follow(): void {
    const page = this.page;
    if (!page) return;
    this.apiService.followPage(page.id).subscribe(() => {
      page.is_following = true;
      page.followers_count++;
      this.followersLoaded = false;
    });
  }

  unfollow(): void {
    const page = this.page;
    if (!page) return;
    this.apiService.unfollowPage(page.id).subscribe(() => {
      page.is_following = false;
      page.followers_count = Math.max(0, page.followers_count - 1);
      this.followersLoaded = false;
    });
  }

  onPageChange(updated: Page): void {
    this.page = { ...this.page, ...updated };
  }

  onDeleted(): void {
    this.snackBar.open('Page deleted', 'Dismiss', { duration: 3000 });
    this.router.navigate(['/pages']);
  }
}
