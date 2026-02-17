import { Component, Input, Output, EventEmitter, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatMenuModule } from '@angular/material/menu';
import { ApiService } from '../../../core/services/api.service';
import { AuthService } from '../../../core/services/auth.service';
import { Post, Comment, REACTIONS } from '../../../models/post.model';

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
  currentUserId: number | null = null;

  constructor(private apiService: ApiService, private authService: AuthService) {}

  ngOnInit(): void {
    this.currentUserId = this.authService.currentUser?.id ?? null;
  }

  get isOwner(): boolean {
    return this.post.author.id === this.currentUserId;
  }

  react(type: string): void {
    this.showReactions = false;
    this.apiService.reactToPost(this.post.id, type).subscribe((res) => {
      this.post.my_reaction = res.reacted ? (res.reaction ?? null) : null;
      // Optimistic count update
      this.post.likes_count += res.reacted ? 1 : -1;
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
