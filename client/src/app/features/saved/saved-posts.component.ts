import { ChangeDetectionStrategy, Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../core/services/api.service';
import { Post } from '../../models/post.model';
import { PostCardComponent } from '../../shared/components/post-card/post-card.component';

/** Your saved posts, most recently saved first. Only you can see this list. */
@Component({
  selector: 'app-saved-posts',
  imports: [CommonModule, RouterLink, MatButtonModule, MatIconModule, MatProgressSpinnerModule, PostCardComponent],
  changeDetection: ChangeDetectionStrategy.Eager,
  template: `
    <main class="saved-page">
      <header class="card saved-header">
        <mat-icon aria-hidden="true">bookmark</mat-icon>
        <div>
          <h1>Saved</h1>
          <p class="text-secondary text-sm">Only you can see what you've saved.</p>
        </div>
      </header>
      <app-post-card *ngFor="let p of posts; trackBy: trackById" [post]="p"
                     (savedChange)="onSavedChange($event)" (postDeleted)="remove($event)"></app-post-card>
      <div *ngIf="loading" class="center"><mat-spinner diameter="32"></mat-spinner></div>
      <section *ngIf="!loading && posts.length === 0" class="card empty">
        <p>Nothing saved yet. Use <strong>Save post</strong> in a post's menu to keep it here.</p>
        <a mat-stroked-button routerLink="/feed">Browse your feed</a>
      </section>
      <button mat-stroked-button *ngIf="hasMore && !loading" (click)="loadMore()">Load more</button>
    </main>
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
  hasMore = false;
  private page = 1;

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this.load();
  }

  private load(): void {
    this.loading = true;
    this.api.getSavedPosts(this.page).subscribe({
      next: (res) => {
        this.posts = [...this.posts, ...res.results];
        this.hasMore = !!res.next;
        this.loading = false;
      },
      error: () => (this.loading = false),
    });
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
