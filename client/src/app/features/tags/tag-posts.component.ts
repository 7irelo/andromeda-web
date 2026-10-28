import { ChangeDetectionStrategy, Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute } from '@angular/router';
import { Subscription } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../core/services/api.service';
import { Post } from '../../models/post.model';
import { PostCardComponent } from '../../shared/components/post-card/post-card.component';
import { EmptyStateComponent, ErrorStateComponent, SkeletonComponent } from '../../shared/components/states';

/** Posts with a hashtag that you're allowed to see, newest first. */
@Component({
  selector: 'app-tag-posts',
  imports: [CommonModule, MatButtonModule, MatIconModule, MatProgressSpinnerModule, PostCardComponent,
    EmptyStateComponent, ErrorStateComponent, SkeletonComponent],
  changeDetection: ChangeDetectionStrategy.Eager,
  template: `
    <div class="tag-page">
      <header class="card tag-header">
        <span class="hash" aria-hidden="true">#</span>
        <div>
          <h1>#{{ tag }}</h1>
          <p class="text-secondary text-sm" *ngIf="count !== null">{{ count }} {{ count === 1 ? 'post' : 'posts' }}</p>
        </div>
      </header>
      <app-post-card *ngFor="let p of posts; trackBy: trackById" [post]="p" (postDeleted)="onDeleted($event)"></app-post-card>
      <app-skeleton *ngIf="loading && posts.length === 0" variant="post" [count]="2"></app-skeleton>
      <div *ngIf="loading && posts.length > 0" class="center"><mat-spinner diameter="32"></mat-spinner></div>
      <app-error-state *ngIf="!loading && loadError" [compact]="posts.length > 0" (retry)="retry()"></app-error-state>
      <app-empty-state *ngIf="!loading && !loadError && posts.length === 0" icon="tag"
                       [title]="'No posts with #' + tag + ' yet'" message="Use the tag in a post to start it off."></app-empty-state>
      <button mat-stroked-button *ngIf="hasMore && !loading && !loadError" (click)="loadMore()">Load more</button>
    </div>
  `,
  styles: [`
    .tag-page { max-width: 640px; margin: 16px auto; padding: 0 16px; display: flex; flex-direction: column; gap: 12px; }
    .tag-header { display: flex; align-items: center; gap: 16px; padding: 16px 20px; h1 { margin: 0; font-size: 22px; } p { margin: 2px 0 0; } }
    .hash {
      width: 48px; height: 48px; border-radius: 50%; background: var(--primary-light); color: var(--primary);
      display: flex; align-items: center; justify-content: center; font-size: 26px; font-weight: 700;
    }
    .center { display: flex; justify-content: center; padding: 24px; }
    .empty { padding: 24px; text-align: center; color: var(--text-secondary); }
  `],
})
export class TagPostsComponent implements OnInit, OnDestroy {
  tag = '';
  posts: Post[] = [];
  count: number | null = null;
  loading = false;
  loadError = false;
  hasMore = false;
  private page = 1;
  private sub?: Subscription;
  private request?: Subscription;

  constructor(private route: ActivatedRoute, private api: ApiService) {}

  ngOnInit(): void {
    this.sub = this.route.paramMap.subscribe((params) => {
      this.tag = (params.get('name') ?? '').replace(/^#/, '').toLowerCase().slice(0, 50);
      this.posts = [];
      this.page = 1;
      this.count = null;
      this.load();
    });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
    this.request?.unsubscribe();
  }

  private load(): void {
    this.request?.unsubscribe();
    if (!this.tag) return;
    this.loading = true;
    this.loadError = false;
    this.request = this.api.getTagPosts(this.tag, this.page).subscribe({
      next: (res) => {
        this.posts = [...this.posts, ...res.results];
        this.count = res.count;
        this.hasMore = !!res.next;
        this.loading = false;
      },
      error: () => {
        this.loading = false;
        this.loadError = true;
      },
    });
  }

  retry(): void {
    this.load();
  }

  loadMore(): void {
    this.page++;
    this.load();
  }

  onDeleted(id: number): void {
    this.posts = this.posts.filter((p) => p.id !== id);
  }

  trackById(_i: number, p: Post): number {
    return p.id;
  }
}
