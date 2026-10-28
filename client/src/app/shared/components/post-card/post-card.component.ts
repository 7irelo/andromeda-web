import { CommonModule, NgOptimizedImage } from '@angular/common';
import { Component, EventEmitter, Input, OnInit, Output, ChangeDetectionStrategy, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatDialog } from '@angular/material/dialog';
import { RouterLink } from '@angular/router';
import { openReportDialog } from '../report-dialog/report-dialog.component';
import { ApiService } from '../../../core/services/api.service';
import { AuthService } from '../../../core/services/auth.service';
import { Post, PostMedia, PostRevision, Reaction, REACTIONS } from '../../../models/post.model';
import { LightboxComponent } from './lightbox.component';
import { PostCommentsComponent } from './post-comments.component';
import { PostTextComponent } from './post-text.component';
import { timeAgo } from './time-ago';

/** Images shown in the card grid; the rest open in the lightbox. */
const GRID_MAX = 4;

@Component({
    selector: 'app-post-card',
    imports: [
      CommonModule, NgOptimizedImage, RouterLink, FormsModule, MatIconModule, MatButtonModule, MatMenuModule,
      LightboxComponent, PostCommentsComponent, PostTextComponent,
    ],
    templateUrl: './post-card.component.html',
    changeDetection: ChangeDetectionStrategy.Eager,
    styleUrls: ['./post-card.component.scss']
})
export class PostCardComponent implements OnInit {
  @Input() post!: Post;
  /** Open the comments straight away (post detail page). */
  @Input() expandComments = false;
  /** Offer "Hide from feed" (home feed only). */
  @Input() allowHide = false;
  @Output() postDeleted = new EventEmitter<number>();
  @Output() postHidden = new EventEmitter<number>();
  @Output() savedChange = new EventEmitter<{ id: number; saved: boolean }>();

  reactions = REACTIONS;
  showComments = false;
  showReactions = false;
  showReason = false;
  lightboxIndex: number | null = null;
  currentUserId: number | null = null;
  gridMax = GRID_MAX;

  editing = false;
  editText = '';
  editMedia: PostMedia[] = [];
  saving = false;
  editError = '';

  revisions: PostRevision[] | null = null;
  showHistory = false;

  reactionByType: Partial<Record<string, Reaction>> = {};
  ago = timeAgo;

  private readonly dialog = inject(MatDialog);

  constructor(private apiService: ApiService, private authService: AuthService) { }

  report(): void {
    openReportDialog(this.dialog, { type: 'post', id: this.post.id, label: 'post' });
  }

  ngOnInit() {
    this.reactionByType = Object.fromEntries(this.reactions.map(r => [r.type, r]));
    this.currentUserId = this.authService.currentUser?.id ?? null;
    this.showComments = this.expandComments;
  }

  get isOwner(): boolean {
    return this.post.author.id === this.currentUserId;
  }

  /** Gallery images in display order, falling back to the legacy single image. */
  get images(): string[] {
    const media = (this.post.media || []).filter((m) => m.media_type === 'image').map((m) => m.file);
    if (media.length) return media;
    return this.post.image ? [this.post.image] : [];
  }

  react(type: string): void {
    this.showReactions = false;
    const hadReaction = !!this.post.my_reaction;
    this.apiService.reactToPost(this.post.id, type).subscribe((res) => {
      this.post.my_reaction = res.reacted ? (res.reaction ?? null) : null;
      // Count changes only when toggling on/off, not when switching reaction type.
      if (!hadReaction && res.reacted) {
        this.post.likes_count++;
      } else if (hadReaction && !res.reacted) {
        this.post.likes_count = Math.max(0, this.post.likes_count - 1);
      }
    });
  }

  toggleComments(): void {
    this.showComments = !this.showComments;
  }

  share(): void {
    this.apiService.sharePost(this.post.id, '').subscribe(() => {
      this.post.shares_count++;
    });
  }

  toggleSave(): void {
    const call = this.post.is_saved ? this.apiService.unsavePost(this.post.id) : this.apiService.savePost(this.post.id);
    call.subscribe((res) => {
      this.post.is_saved = res.saved;
      this.savedChange.emit({ id: this.post.id, saved: res.saved });
    });
  }

  hide(): void {
    this.apiService.hidePost(this.post.id).subscribe(() => this.postHidden.emit(this.post.id));
  }

  deletePost(): void {
    if (!confirm('Delete this post?')) return;
    this.apiService.deletePost(this.post.id).subscribe(() => {
      this.postDeleted.emit(this.post.id);
    });
  }

  // ── Editing ────────────────────────────────────────────────────────────

  startEdit(): void {
    this.editing = true;
    this.editText = this.post.content;
    this.editMedia = [...(this.post.media || [])];
    this.editError = '';
  }

  moveMedia(index: number, delta: number): void {
    const target = index + delta;
    if (target < 0 || target >= this.editMedia.length) return;
    const copy = [...this.editMedia];
    [copy[index], copy[target]] = [copy[target], copy[index]];
    this.editMedia = copy;
  }

  removeMedia(index: number): void {
    this.editMedia = this.editMedia.filter((_, i) => i !== index);
  }

  saveEdit(): void {
    const original = (this.post.media || []).map((m) => m.id).join(',');
    const order = this.editMedia.map((m) => m.id);
    const data: Partial<Post> & { media_order?: number[] } = { content: this.editText };
    if (order.join(',') !== original) data.media_order = order;
    if (!this.editText.trim() && !order.length && !this.post.image && !this.post.video && !this.post.shared_post) {
      this.editError = 'A post needs some text or an image.';
      return;
    }
    this.saving = true;
    this.apiService.updatePost(this.post.id, data).subscribe({
      next: (updated) => {
        Object.assign(this.post, updated);
        this.editing = false;
        this.saving = false;
        this.revisions = null;
      },
      error: () => {
        this.saving = false;
        this.editError = 'Your changes could not be saved.';
      },
    });
  }

  toggleHistory(): void {
    this.showHistory = !this.showHistory;
    if (this.showHistory && this.revisions === null) {
      this.apiService.getPostRevisions(this.post.id).subscribe((r) => (this.revisions = r));
    }
  }

  get privacyIcon(): string {
    return { public: 'public', friends: 'group', private: 'lock' }[this.post.privacy] ?? 'public';
  }

  openLightbox(index: number): void {
    this.lightboxIndex = index;
  }
}
