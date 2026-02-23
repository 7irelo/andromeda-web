import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, OnInit, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../../core/services/api.service';
import { AuthService } from '../../../core/services/auth.service';
import { Comment, Post, Reaction, REACTIONS } from '../../../models/post.model';

@Component({
  selector: 'app-post-card',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule, MatIconModule, MatButtonModule, MatMenuModule],
  templateUrl: './post-card.component.html',
  styleUrls: ['./post-card.component.scss'],
})
export class PostCardComponent implements OnInit {
  @Input() post!: Post;
  @Output() postDeleted = new EventEmitter<number>();

  reactions = REACTIONS;
  comments: Comment[] = [];
  showComments = false;
  commentText = '';
  showReactions = false;
  expandedImage: string | null = null;
  currentUserId: number | null = null;

  constructor(private apiService: ApiService, private authService: AuthService) { }

    reactionByType: Partial<Record<string, Reaction>> = {};

  ngOnInit() {
    this.reactionByType = Object.fromEntries(this.reactions.map(r => [r.type, r]));
    this.currentUserId = this.authService.currentUser?.id ?? null;
  }

  get isOwner(): boolean {
    return this.post.author.id === this.currentUserId;
  }

  get currentUserAvatarUrl(): string {
    return this.authService.currentUser?.avatar_url ?? 'assets/default-avatar.png';
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
    if (this.showComments && this.comments.length === 0) {
      this.loadComments();
    }
  }

  loadComments(): void {
    this.apiService.getComments(this.post.id).subscribe((c) => (this.comments = c));
  }

  submitComment(): void {
    if (!this.commentText.trim()) return;
    this.apiService.createComment(this.post.id, { content: this.commentText }).subscribe((c) => {
      this.comments.push(c);
      this.post.comments_count++;
      this.commentText = '';
    });
  }

  share(): void {
    this.apiService.sharePost(this.post.id, '').subscribe((p) => {
      console.log('Shared', p);
      this.post.shares_count++;
    });
  }

  deletePost(): void {
    this.apiService.deletePost(this.post.id).subscribe(() => {
      this.postDeleted.emit(this.post.id);
    });
  }

  timeAgo(dateStr: string): string {
    const now = Date.now();
    const diff = (now - new Date(dateStr).getTime()) / 1000;
    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
    if (diff < 604800) return `${Math.floor(diff / 86400)}d`;
    return new Date(dateStr).toLocaleDateString();
  }
}
