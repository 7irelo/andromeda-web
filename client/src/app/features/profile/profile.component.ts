import { Component, Input, OnInit, OnChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTabsModule } from '@angular/material/tabs';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { User } from '../../models/user.model';
import { Post } from '../../models/post.model';
import { PostCardComponent } from '../../shared/components/post-card/post-card.component';

@Component({
  selector: 'app-profile',
  standalone: true,
  imports: [CommonModule, MatButtonModule, MatIconModule, MatTabsModule, MatProgressSpinnerModule, PostCardComponent],
  templateUrl: './profile.component.html',
  styleUrls: ['./profile.component.scss'],
})
export class ProfileComponent implements OnInit, OnChanges {
  @Input() username!: string;

  profile: User | null = null;
  posts: Post[] = [];
  loading = false;
  currentUser: User | null = null;
  isSelf = false;

  constructor(private apiService: ApiService, private authService: AuthService) {}

  ngOnInit(): void {
    this.currentUser = this.authService.currentUser;
    this.loadProfile();
  }

  ngOnChanges(): void {
    this.loadProfile();
  }

  loadProfile(): void {
    if (!this.username) return;
    this.loading = true;
    this.apiService.getUser(this.username).subscribe({
      next: (user) => {
        this.profile = user;
        this.isSelf = user.id === this.currentUser?.id;
        this.loading = false;
        this.loadPosts(user.id);
      },
      error: () => (this.loading = false),
    });
  }

  loadPosts(userId: number): void {
    this.apiService.getPosts({ author: userId.toString() }).subscribe({
      next: (res) => (this.posts = res.results),
    });
  }

  follow(): void {
    if (!this.profile) return;
    if (this.profile.is_following) {
      this.apiService.unfollowUser(this.profile.id).subscribe(() => {
        if (this.profile) { this.profile.is_following = false; this.profile.followers_count--; }
      });
    } else {
      this.apiService.followUser(this.profile.id).subscribe(() => {
        if (this.profile) { this.profile.is_following = true; this.profile.followers_count++; }
      });
    }
  }

  addFriend(): void {
    if (!this.profile) return;
    this.apiService.sendFriendRequest(this.profile.id).subscribe();
  }

  onPostDeleted(postId: number): void {
    this.posts = this.posts.filter((p) => p.id !== postId);
  }
}
