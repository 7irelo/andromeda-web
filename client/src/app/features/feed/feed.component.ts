import { Component, OnInit, HostListener } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { WebSocketService } from '../../core/services/websocket.service';
import { Post } from '../../models/post.model';
import { User } from '../../models/user.model';
import { PostCardComponent } from '../../shared/components/post-card/post-card.component';
import { CreatePostComponent } from '../../shared/components/create-post/create-post.component';
import { UserCardComponent } from '../../shared/components/user-card/user-card.component';

@Component({
  selector: 'app-feed',
  standalone: true,
  imports: [
    CommonModule, RouterLink, RouterLinkActive, MatProgressSpinnerModule, MatButtonModule,
    MatIconModule, PostCardComponent, CreatePostComponent, UserCardComponent,
  ],
  templateUrl: './feed.component.html',
  styleUrls: ['./feed.component.scss'],
})
export class FeedComponent implements OnInit {
  posts: Post[] = [];
  suggestions: User[] = [];
  currentUser: User | null = null;
  loading = false;
  page = 1;
  hasMore = true;

  constructor(
    private apiService: ApiService,
    private authService: AuthService,
    private wsService: WebSocketService,
  ) {}

  ngOnInit(): void {
    this.currentUser = this.authService.currentUser;
    this.loadFeed();
    this.loadSuggestions();

    // Show new notifications in real time
    this.wsService.notification$.subscribe((notif) => {
      console.log('New notification:', notif);
    });
  }

  loadFeed(): void {
    if (this.loading || !this.hasMore) return;
    this.loading = true;

    this.apiService.getFeed(this.page).subscribe({
      next: (res) => {
        this.posts = [...this.posts, ...res.results];
        this.hasMore = !!res.next;
        this.page++;
        this.loading = false;
      },
      error: () => (this.loading = false),
    });
  }

  loadSuggestions(): void {
    this.apiService.getSuggestions().subscribe({
      next: (users) => (this.suggestions = users.slice(0, 5)),
      error: () => {},
    });
  }

  onPostCreated(post: Post): void {
    this.posts.unshift(post);
  }

  onPostDeleted(postId: number): void {
    this.posts = this.posts.filter((p) => p.id !== postId);
  }

  @HostListener('window:scroll')
  onWindowScroll(): void {
    const scrolled = window.scrollY + window.innerHeight;
    const height = document.documentElement.scrollHeight;
    if (scrolled >= height - 400 && !this.loading && this.hasMore) {
      this.loadFeed();
    }
  }

  trackById(_index: number, post: Post): number {
    return post.id;
  }
}
