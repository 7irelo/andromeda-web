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
    <div class="page-detail" *ngIf="page">
      <div class="cover">
        <img [src]="page.cover_photo || 'assets/default-cover.png'" alt="" />
      </div>
      <div class="header">
        <img class="avatar-lg" [src]="page.avatar || 'assets/default-avatar.png'" [alt]="page.name" />
        <div class="title">
          <h1>
            {{ page.name }}
            <mat-icon class="verified" *ngIf="page.is_verified" matTooltip="Verified page" aria-label="Verified">verified</mat-icon>
          </h1>
          <p class="text-secondary text-sm">&#64;{{ page.username }} · {{ categoryLabel }} · {{ page.followers_count | number }} followers</p>
        </div>
        <div class="header-actions">
          <button mat-flat-button color="primary" *ngIf="!page.is_following" (click)="follow()">
            <mat-icon>add</mat-icon> Follow
          </button>
          <button mat-stroked-button *ngIf="page.is_following" (click)="unfollow()">
            <mat-icon>check</mat-icon> Following
          </button>
        </div>
      </div>

      <mat-tab-group animationDuration="0ms" (selectedIndexChange)="onTab($event)">
        <mat-tab label="Posts">
          <div class="tab-body">
            <app-post-card *ngFor="let p of posts" [post]="p" (postDeleted)="onPostDeleted($event)"></app-post-card>
            <p class="text-secondary" *ngIf="postsLoaded && posts.length === 0">No posts yet.</p>
            <button mat-stroked-button *ngIf="postsNext" (click)="loadPosts(postsPage + 1)">Load more</button>
          </div>
        </mat-tab>

        <mat-tab label="About">
          <div class="tab-body">
            <div class="card section">
              <h3>About</h3>
              <p class="text-secondary">{{ page.description || 'No description yet.' }}</p>
              <ul class="contact">
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
            <div class="followers-grid">
              <a *ngFor="let u of followers" class="member-card" [routerLink]="'/profile/' + u.username">
                <img [src]="u.avatar_url || 'assets/default-avatar.png'" class="avatar md" [alt]="u.username" />
                <span class="font-semibold text-sm">{{ u.full_name }}</span>
              </a>
            </div>
            <p class="text-secondary" *ngIf="followersLoaded && followers.length === 0">No followers yet.</p>
            <button mat-stroked-button *ngIf="followersNext" (click)="loadFollowers(followersPage + 1)">Load more</button>
          </div>
        </mat-tab>

        <mat-tab label="Manage" *ngIf="page.my_role">
          <div class="tab-body">
            <app-page-manage [page]="page" (pageChange)="onPageChange($event)" (deleted)="onDeleted()"></app-page-manage>
          </div>
        </mat-tab>
      </mat-tab-group>
    </div>

    <div class="loading-center" *ngIf="loading"><mat-spinner diameter="40"></mat-spinner></div>
    <div class="empty-state" *ngIf="notFound">
      <mat-icon>auto_stories</mat-icon>
      <p>This page doesn't exist.</p>
      <a mat-stroked-button routerLink="/pages">Browse pages</a>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    .page-detail { max-width: 860px; margin: 0 auto; padding: 16px; }
    .cover { height: 220px; border-radius: 16px; overflow: hidden; background: var(--gradient-accent); }
    .cover img { width: 100%; height: 100%; object-fit: cover; }
    .header { display: flex; align-items: flex-end; gap: 16px; padding: 0 16px; margin-top: -40px; flex-wrap: wrap; }
    .avatar-lg {
      width: 96px; height: 96px; border-radius: 20px; object-fit: cover;
      border: 4px solid var(--surface); box-shadow: var(--shadow); background: var(--surface);
    }
    .title { flex: 1; min-width: 200px; padding-bottom: 4px; }
    .title h1 { font-size: 24px; font-weight: 800; display: flex; align-items: center; gap: 6px; }
    .verified { color: var(--primary); }
    .header-actions { padding-bottom: 8px; }
    .tab-body { display: flex; flex-direction: column; gap: 16px; padding: 16px 0; }
    .section { padding: 16px 20px; }
    .section h3 { font-size: 16px; font-weight: 700; margin-bottom: 8px; }
    .contact { list-style: none; padding: 0; margin-top: 12px; display: flex; flex-direction: column; gap: 8px; }
    .contact li { display: flex; align-items: center; gap: 8px; }
    .contact mat-icon { font-size: 18px; width: 18px; height: 18px; opacity: .7; }
    .followers-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
    .member-card {
      display: flex; align-items: center; gap: 10px; padding: 10px 12px;
      background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
      text-decoration: none; color: inherit;
    }
    .loading-center { display: flex; justify-content: center; padding: 60px; }
    .empty-state { display: flex; flex-direction: column; align-items: center; padding: 60px; gap: 12px; color: var(--text-secondary); }
    .empty-state mat-icon { font-size: 48px; width: 48px; height: 48px; opacity: .4; }
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
