import { ChangeDetectionStrategy, Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../core/services/api.service';
import { Post } from '../../models/post.model';
import { PostCardComponent } from '../../shared/components/post-card/post-card.component';
import { EmptyStateComponent, ErrorStateComponent, SkeletonComponent } from '../../shared/components/states';

/** Your saved posts, most recently saved first. Only you can see this list. */
@Component({
  selector: 'app-saved-posts',
  imports: [CommonModule, RouterLink, MatButtonModule, MatIconModule, MatProgressSpinnerModule, PostCardComponent,
    EmptyStateComponent, ErrorStateComponent, SkeletonComponent],
  changeDetection: ChangeDetectionStrategy.Eager,
  template: `
    <div class="saved-page">
      <header class="card saved-header">
        <mat-icon aria-hidden="true">bookmark</mat-icon>
        <div>
          <h1>Saved</h1>
          <p class="text-secondary text-sm">Only you can see what you've saved.</p>
        </div>
      </header>
      <app-post-card *ngFor="let p of posts; trackBy: trackById" [post]="p"
                     (savedChange)="onSavedChange($event)" (postDeleted)="remove($event)"></app-post-card>
      <app-skeleton *ngIf="loading && posts.length === 0" variant="post" [count]="2"></app-skeleton>
      <div *ngIf="loading && posts.length > 0" class="center"><mat-spinner diameter="32"></mat-spinner></div>
      <app-error-state *ngIf="!loading && loadError" [compact]="posts.length > 0" (retry)="retry()"></app-error-state>
      <app-empty-state *ngIf="!loading && !loadError && posts.length === 0" icon="bookmark_border" title="Nothing saved yet"
                       message="Use Save post in a post's menu to keep it here.">
        <a mat-stroked-button routerLink="/feed">Browse your feed</a>
      </app-empty-state>
      <button mat-stroked-button *ngIf="hasMore && !loading && !loadError" (click)="loadMore()">Load more</button>
    </div>
  `,
  styles: [`
    .saved-page { max-width: 640px; margin: 16px auto; padding: 0 16px; display: flex; flex-direction: column; gap: 12px; }
    .saved-header {
      display: flex; align-items: center; gap: 16px; padding: 16px 20px;
      h1 { margin: 0; font-size: 22px; } p { margin: 2px 0 0; }
      mat-icon { color: var(--primary); font-size: 32px; width: 32px; height: 32px; }
    }
    .center { display: flex; justify-content: center; padding: 24px; }
    .empty { padding: 24px; text-align: center; color: var(--text-secondary); }
  `],
})
export class SavedPostsComponent implements OnInit {
  posts: Post[] = [];
  loading = false;
  loadError = false;
  hasMore = false;
  private page = 1;

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this.load();
  }

  private load(): void {
    this.loading = true;
    this.loadError = false;
    this.api.getSavedPosts(this.page).subscribe({
      next: (res) => {
        this.posts = [...this.posts, ...res.results];
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

  onSavedChange(change: { id: number; saved: boolean }): void {
    if (!change.saved) this.remove(change.id);
  }

  remove(id: number): void {
    this.posts = this.posts.filter((p) => p.id !== id);
  }

  trackById(_i: number, p: Post): number {
    return p.id;
  }
}
