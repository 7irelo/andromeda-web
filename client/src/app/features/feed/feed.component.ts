import {
  AfterViewInit, ChangeDetectionStrategy, Component, ElementRef, HostListener, NgZone, OnDestroy, OnInit, QueryList,
  ViewChildren, inject,
} from '@angular/core';
import { CommonModule, NgOptimizedImage } from '@angular/common';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { Subscription } from 'rxjs';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { WebSocketService } from '../../core/services/websocket.service';
import { FeedSort, Post } from '../../models/post.model';
import { User } from '../../models/user.model';
import { PostCardComponent } from '../../shared/components/post-card/post-card.component';
import { CreatePostComponent } from '../../shared/components/create-post/create-post.component';
import { UserCardComponent } from '../../shared/components/user-card/user-card.component';
import { DwellTracker } from './dwell-tracker';
import { EmptyStateComponent, ErrorStateComponent, SkeletonComponent } from '../../shared/components/states';

const SORT_KEY = 'andromeda.feedSort';
/** How often seen/opened posts are reported to the ranker (and once more when the page is hidden). */
const FLUSH_MS = 10_000;

@Component({
    selector: 'app-feed',
    imports: [
        CommonModule, NgOptimizedImage, RouterLink, RouterLinkActive, MatProgressSpinnerModule, MatButtonModule,
        MatIconModule, MatSnackBarModule, PostCardComponent, CreatePostComponent, UserCardComponent,
        EmptyStateComponent, ErrorStateComponent, SkeletonComponent,
    ],
    templateUrl: './feed.component.html',
    changeDetection: ChangeDetectionStrategy.Eager,
    styleUrls: ['./feed.component.scss']
})
export class FeedComponent implements OnInit, AfterViewInit, OnDestroy {
  posts: Post[] = [];
  suggestions: User[] = [];
  currentUser: User | null = null;
  loading = false;
  loadError = false;
  hasMore = true;
  sort: FeedSort = 'top';
  /** Ids of friends' posts announced over the socket that aren't on screen yet. */
  newPostIds = new Set<number>();

  private cursor: string | null = null;
  private request?: Subscription;
  private wsSub?: Subscription;

  // Dwell / open reporting: the ranker's training signal.
  @ViewChildren(PostCardComponent, { read: ElementRef }) private cards?: QueryList<ElementRef<HTMLElement>>;
  private readonly tracker = new DwellTracker();
  private observer?: IntersectionObserver;
  private observed = new Set<HTMLElement>();
  private cardsSub?: Subscription;
  private flushTimer?: ReturnType<typeof setInterval>;
  private zone = inject(NgZone);

  constructor(
    private apiService: ApiService,
    private authService: AuthService,
    private wsService: WebSocketService,
    private snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.currentUser = this.authService.currentUser;
    try {
      const saved = localStorage.getItem(SORT_KEY);
      if (saved === 'top' || saved === 'latest') this.sort = saved;
    } catch { /* storage unavailable: keep the default */ }
    this.loadFeed();
    this.loadSuggestions();

    this.wsSub = this.wsService.feedNewPost$.subscribe((postId) => {
      if (!this.posts.some((p) => p.id === postId)) {
        this.newPostIds = new Set(this.newPostIds).add(postId);
      }
    });
  }

  ngAfterViewInit(): void {
    if (typeof IntersectionObserver === 'undefined' || !this.cards) return;
    this.observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        const id = Number((entry.target as HTMLElement).dataset['postId']);
        if (id) this.tracker.visible(id, entry.isIntersecting && entry.intersectionRatio >= 0.5);
      }
    }, { threshold: [0, 0.5] });
    this.observeCards();
    this.cardsSub = this.cards.changes.subscribe(() => this.observeCards());
    // Outside the zone: a background timer shouldn't trigger change detection or keep the app unstable.
    this.flushTimer = this.zone.runOutsideAngular(() => setInterval(() => this.flushEvents(), FLUSH_MS));
  }

  ngOnDestroy(): void {
    this.flushEvents();
    this.observer?.disconnect();
    this.cardsSub?.unsubscribe();
    if (this.flushTimer) clearInterval(this.flushTimer);
    this.wsSub?.unsubscribe();
    this.request?.unsubscribe();
  }

  /** Start observing newly rendered post cards and stop observing removed ones. */
  private observeCards(): void {
    if (!this.observer || !this.cards) return;
    const current = new Set(this.cards.map((ref) => ref.nativeElement));
    for (const el of this.observed) {
      if (!current.has(el)) {
        this.observer.unobserve(el);
        this.observed.delete(el);
      }
    }
    for (const el of current) {
      if (!this.observed.has(el)) {
        this.observer.observe(el);
        this.observed.add(el);
      }
    }
  }

  onCardClick(postId: number): void {
    this.tracker.open(postId);
  }

  /**
   * Send what changed since the last batch. A normal authenticated POST:
   * sendBeacon can't carry the bearer token, so the hidden-page flush is a
   * best effort like the rest.
   */
  private flushEvents(): void {
    const events = this.tracker.drain();
    if (events.length) this.apiService.reportFeedEvents(events).subscribe({ error: () => {} });
  }

  @HostListener('document:visibilitychange')
  onVisibilityChange(): void {
    if (document.visibilityState === 'hidden') {
      this.tracker.pause();
      this.flushEvents();
    } else {
      this.tracker.resume();
    }
  }

  loadFeed(): void {
    if (this.loading || !this.hasMore) return;
    this.loading = true;
    this.loadError = false;

    this.request = this.apiService.getFeed(this.sort, this.cursor).subscribe({
      next: (res) => {
        // Engagement can shift between ranked pages; never show a post twice.
        const seen = new Set(this.posts.map((p) => p.id));
        this.posts = [...this.posts, ...res.results.filter((p) => !seen.has(p.id))];
        this.cursor = res.next_cursor;
        this.hasMore = !!res.next_cursor;
        this.loading = false;
      },
      error: () => {
        this.loading = false;
        this.loadError = true;
      },
    });
  }

  /** After a failed page: try the same page again. */
  retry(): void {
    this.loadError = false;
    this.loadFeed();
  }

  /** Start over from the top: on sort change or when the reader asks for the new posts. */
  reload(): void {
    this.request?.unsubscribe();
    this.posts = [];
    this.cursor = null;
    this.hasMore = true;
    this.loading = false;
    this.newPostIds = new Set();
    this.loadFeed();
  }

  setSort(sort: FeedSort): void {
    if (sort === this.sort) return;
    this.sort = sort;
    try { localStorage.setItem(SORT_KEY, sort); } catch { /* ignore */ }
    this.reload();
  }

  showNewPosts(): void {
    window.scrollTo({ top: 0, behavior: 'smooth' });
    this.reload();
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

  onPostHidden(postId: number): void {
    const index = this.posts.findIndex((p) => p.id === postId);
    if (index < 0) return;
    const [post] = this.posts.splice(index, 1);
    this.posts = [...this.posts];
    this.snackBar.open($localize`:@@feed.postHidden:Post hidden from your feed`, $localize`:@@feed.undo:Undo`, { duration: 5000 }).onAction().subscribe(() => {
      this.apiService.unhidePost(postId).subscribe(() => {
        const copy = [...this.posts];
        copy.splice(Math.min(index, copy.length), 0, post);
        this.posts = copy;
      });
    });
  }

  @HostListener('window:scroll')
  onWindowScroll(): void {
    const scrolled = window.scrollY + window.innerHeight;
    const height = document.documentElement.scrollHeight;
    if (scrolled >= height - 400 && !this.loading && !this.loadError && this.hasMore) {
      this.loadFeed();
    }
  }

  trackById(_index: number, post: Post): number {
    return post.id;
  }
}
