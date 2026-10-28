import { ChangeDetectionStrategy, Component, ElementRef, EventEmitter, Input, OnInit, Output } from '@angular/core';
import { CommonModule, NgOptimizedImage } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { ApiService } from '../../../core/services/api.service';
import { AuthService } from '../../../core/services/auth.service';
import { Comment, Post } from '../../../models/post.model';
import { PostTextComponent } from './post-text.component';
import { timeAgo } from './time-ago';

/** Comments under a post: likes, one level of replies, and edit/delete where the server allows it. */
@Component({
  selector: 'app-post-comments',
  imports: [CommonModule, NgOptimizedImage, FormsModule, RouterLink, MatButtonModule, MatIconModule, MatMenuModule, PostTextComponent],
  changeDetection: ChangeDetectionStrategy.Eager,
  template: `
    <div class="comments-section">
      <p *ngIf="loading" class="text-secondary text-sm">Loading comments…</p>
      <p *ngIf="error" class="text-secondary text-sm" role="alert">{{ error }}</p>

      <ng-container *ngFor="let comment of comments; trackBy: trackById">
        <ng-container *ngTemplateOutlet="commentTpl; context: { $implicit: comment, top: comment }"></ng-container>
        <div class="replies" *ngIf="comment.replies.length || replyingTo === comment.id">
          <ng-container *ngFor="let reply of comment.replies; trackBy: trackById">
            <ng-container *ngTemplateOutlet="commentTpl; context: { $implicit: reply, top: comment }"></ng-container>
          </ng-container>
          <form class="comment-input reply-input" *ngIf="replyingTo === comment.id" (ngSubmit)="submitReply(comment)">
            <img [src]="currentUserAvatarUrl" class="avatar sm" alt="" />
            <input type="text" name="reply" [(ngModel)]="replyText" class="comment-field" maxlength="5000"
                   [attr.aria-label]="'Reply to ' + comment.author.full_name" placeholder="Write a reply…"
                   (keydown.escape)="replyingTo = null" #replyField />
            <button mat-icon-button type="submit" [disabled]="!replyText.trim()" aria-label="Send reply">
              <mat-icon>send</mat-icon>
            </button>
          </form>
        </div>
      </ng-container>

      <form class="comment-input" (ngSubmit)="submitComment()">
        <img [src]="currentUserAvatarUrl" class="avatar sm" alt="" />
        <input type="text" name="comment" [(ngModel)]="commentText" placeholder="Write a comment…"
               class="comment-field" maxlength="5000" aria-label="Write a comment" />
        <button mat-icon-button type="submit" [disabled]="!commentText.trim()" aria-label="Send comment">
          <mat-icon>send</mat-icon>
        </button>
      </form>
    </div>

    <ng-template #commentTpl let-c let-top="top">
      <div class="comment" [class.reply]="c.parent">
        <img [ngSrc]="c.author.avatar_url || 'assets/default-avatar.png'" width="32" height="32" class="avatar sm" [alt]="c.author.username" />
        <div class="comment-body">
          <div class="comment-bubble" *ngIf="editingId !== c.id; else editTpl">
            <a [routerLink]="'/profile/' + c.author.username" class="author-name">{{ c.author.full_name }}</a>
            <p><app-post-text [text]="c.content"></app-post-text></p>
          </div>
          <ng-template #editTpl>
            <form class="comment-input" (ngSubmit)="saveEdit(c)">
              <input type="text" name="edit" [(ngModel)]="editText" class="comment-field" maxlength="5000"
                     aria-label="Edit comment" (keydown.escape)="editingId = null" />
              <button mat-button type="submit" [disabled]="!editText.trim()">Save</button>
              <button mat-button type="button" (click)="editingId = null">Cancel</button>
            </form>
          </ng-template>
          <div class="comment-meta">
            <button type="button" class="link-btn" [class.active]="c.liked" (click)="toggleLike(c)"
                    [attr.aria-pressed]="!!c.liked">Like</button>
            <button type="button" class="link-btn" (click)="startReply(top)">Reply</button>
            <span class="text-xs text-secondary">{{ ago(c.created_at) }}</span>
            <span class="text-xs text-secondary" *ngIf="c.is_edited">· edited</span>
            <span class="text-xs likes" *ngIf="c.likes_count > 0" [attr.aria-label]="c.likes_count + ' likes'">
              👍 {{ c.likes_count }}
            </span>
            <ng-container *ngIf="c.author.id === currentUserId || c.can_delete">
              <button mat-icon-button class="more" [matMenuTriggerFor]="menu" aria-label="Comment options">
                <mat-icon>more_horiz</mat-icon>
              </button>
              <mat-menu #menu="matMenu">
                <button mat-menu-item *ngIf="c.author.id === currentUserId" (click)="startEdit(c)">
                  <mat-icon>edit</mat-icon> Edit
                </button>
                <button mat-menu-item *ngIf="c.author.id === currentUserId || c.can_delete" (click)="remove(c, top)">
                  <mat-icon color="warn">delete</mat-icon> Delete
                </button>
              </mat-menu>
            </ng-container>
          </div>
        </div>
      </div>
    </ng-template>
  `,
  styles: [`
    .comments-section { padding: 8px 16px 12px; display: flex; flex-direction: column; gap: 8px; }
    .comment { display: flex; gap: 8px; align-items: flex-start; }
    .comment-body { flex: 1; min-width: 0; }
    .comment-bubble {
      background: var(--bg); border-radius: 14px; padding: 8px 12px; display: inline-block; max-width: 100%;
      p { margin: 2px 0 0; font-size: 14px; }
    }
    .author-name { font-weight: 600; font-size: 13px; color: var(--text-primary); text-decoration: none; }
    .comment-meta { display: flex; align-items: center; gap: 10px; padding: 2px 8px; flex-wrap: wrap; }
    .link-btn {
      background: none; border: none; padding: 0; cursor: pointer; font-size: 12px; font-weight: 600;
      color: var(--text-secondary);
      &.active { color: var(--primary); }
      &:hover, &:focus-visible { text-decoration: underline; }
    }
    .likes { color: var(--text-secondary); }
    .more { width: 28px; height: 28px; padding: 2px; mat-icon { font-size: 18px; } }
    .replies { margin-left: 40px; display: flex; flex-direction: column; gap: 8px; }
    .comment-input { display: flex; align-items: center; gap: 8px; }
    .comment-field {
      flex: 1; border: 1px solid var(--border); background: var(--bg); color: var(--text-primary);
      border-radius: 18px; padding: 8px 14px; font: inherit; font-size: 14px; outline: none;
      &:focus { box-shadow: var(--shadow-glow); }
    }
  `],
})
export class PostCommentsComponent implements OnInit {
  @Input() post!: Post;
  @Output() countChange = new EventEmitter<number>();

  comments: Comment[] = [];
  loading = false;
  error = '';
  commentText = '';
  replyText = '';
  replyingTo: number | null = null;
  editingId: number | null = null;
  editText = '';
  currentUserId: number | null = null;
  ago = timeAgo;

  constructor(private api: ApiService, private auth: AuthService, private host: ElementRef<HTMLElement>) {}

  get currentUserAvatarUrl(): string {
    return this.auth.currentUser?.avatar_url ?? 'assets/default-avatar.png';
  }

  ngOnInit(): void {
    this.currentUserId = this.auth.currentUser?.id ?? null;
    this.load();
  }

  load(): void {
    this.loading = true;
    this.api.getComments(this.post.id).subscribe({
      next: (c) => {
        this.comments = c;
        this.loading = false;
      },
      error: () => {
        this.loading = false;
        this.error = 'Comments could not be loaded.';
      },
    });
  }

  private bump(delta: number): void {
    this.countChange.emit(Math.max(0, this.post.comments_count + delta));
  }

  submitComment(): void {
    const content = this.commentText.trim();
    if (!content) return;
    this.api.createComment(this.post.id, { content }).subscribe((c) => {
      this.comments.push(c);
      this.commentText = '';
      this.bump(1);
    });
  }

  startReply(top: Comment): void {
    this.replyingTo = top.id;
    this.replyText = '';
    setTimeout(() => this.host.nativeElement.querySelector<HTMLInputElement>('.reply-input input')?.focus());
  }

  submitReply(top: Comment): void {
    const content = this.replyText.trim();
    if (!content) return;
    this.api.createComment(this.post.id, { content, parent: top.id }).subscribe((c) => {
      top.replies = [...top.replies, c];
      this.replyText = '';
      this.replyingTo = null;
      this.bump(1);
    });
  }

  toggleLike(c: Comment): void {
    this.api.likeComment(c.id).subscribe((res) => {
      c.liked = res.liked;
      c.likes_count = res.likes_count;
    });
  }

  startEdit(c: Comment): void {
    this.editingId = c.id;
    this.editText = c.content;
  }

  saveEdit(c: Comment): void {
    const content = this.editText.trim();
    if (!content) return;
    this.api.updateComment(c.id, content).subscribe((updated) => {
      c.content = updated.content;
      c.is_edited = updated.is_edited;
      this.editingId = null;
    });
  }

  remove(c: Comment, top: Comment): void {
    if (!confirm('Delete this comment?')) return;
    this.api.deleteComment(c.id).subscribe(() => {
      if (c === top) {
        this.comments = this.comments.filter((x) => x.id !== c.id);
        this.bump(-(1 + c.replies.length));
      } else {
        top.replies = top.replies.filter((x) => x.id !== c.id);
        this.bump(-1);
      }
    });
  }

  trackById(_i: number, c: Comment): number {
    return c.id;
  }
}
