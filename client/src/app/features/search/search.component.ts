import { Component, OnDestroy, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { Subscription, switchMap, of, catchError } from 'rxjs';
import { ApiService } from '../../core/services/api.service';
import { SearchResponse, SearchType } from '../../models/search.model';
import { PostCardComponent } from '../../shared/components/post-card/post-card.component';

@Component({
    selector: 'app-search',
    imports: [CommonModule, RouterLink, MatButtonToggleModule, MatIconModule, MatProgressSpinnerModule, PostCardComponent],
    template: `
    <div class="search-page">
      <h1>Results for “{{ query }}”</h1>
      <mat-button-toggle-group [value]="type" (change)="setType($event.value)" class="tabs" aria-label="Result type">
        <mat-button-toggle *ngFor="let t of types" [value]="t">{{ t | titlecase }}</mat-button-toggle>
      </mat-button-toggle-group>

      <div class="loading-center" *ngIf="loading"><mat-spinner diameter="40"></mat-spinner></div>

      <ng-container *ngIf="!loading && data">
        <section *ngIf="data.results.people?.length">
          <h2>People</h2>
          <a class="row card" *ngFor="let u of data.results.people" [routerLink]="'/profile/' + u.username">
            <img [src]="u.avatar_url || 'assets/default-avatar.png'" class="avatar md" alt="" />
            <div><div class="font-semibold">{{ u.full_name }}</div><div class="text-secondary text-sm">&#64;{{ u.username }}</div></div>
          </a>
        </section>

        <section *ngIf="data.results.posts?.length">
          <h2>Posts</h2>
          <app-post-card *ngFor="let p of data.results.posts" [post]="p"></app-post-card>
        </section>

        <section *ngIf="data.results.groups?.length">
          <h2>Groups</h2>
          <a class="row card" *ngFor="let g of data.results.groups" [routerLink]="'/groups/' + g.id">
            <mat-icon>groups</mat-icon>
            <div><div class="font-semibold">{{ g.name }}</div><div class="text-secondary text-sm">{{ g.members_count }} members · {{ g.privacy | titlecase }}</div></div>
          </a>
        </section>

        <section *ngIf="data.results.pages?.length">
          <h2>Pages</h2>
          <div class="row card" *ngFor="let p of data.results.pages">
            <mat-icon>flag</mat-icon>
            <div><div class="font-semibold">{{ p.name }}</div><div class="text-secondary text-sm">{{ p.followers_count }} followers</div></div>
          </div>
        </section>

        <section *ngIf="data.results.listings?.length">
          <h2>Marketplace</h2>
          <a class="row card" *ngFor="let l of data.results.listings" [routerLink]="'/marketplace/' + l.id">
            <mat-icon>storefront</mat-icon>
            <div><div class="font-semibold">{{ l.title }}</div><div class="text-secondary text-sm">{{ l.currency }} {{ l.price }}</div></div>
          </a>
        </section>

        <section *ngIf="data.results.videos?.length">
          <h2>Videos</h2>
          <a class="row card" *ngFor="let v of data.results.videos" [routerLink]="'/watch/' + v.id">
            <mat-icon>smart_display</mat-icon>
            <div class="font-semibold">{{ v.title }}</div>
          </a>
        </section>

        <p class="text-secondary empty" *ngIf="isEmpty">Nothing matched “{{ query }}”.</p>
      </ng-container>
      <p class="text-secondary empty" *ngIf="error">{{ error }}</p>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    .search-page { max-width: 720px; margin: 0 auto; padding: 24px 16px; }
    h1 { font-size: 22px; margin-bottom: 16px; }
    h2 { font-size: 16px; margin: 24px 0 8px; }
    .tabs { flex-wrap: wrap; }
    section { display: flex; flex-direction: column; gap: 8px; }
    .row { display: flex; align-items: center; gap: 12px; padding: 12px; color: inherit; text-decoration: none; }
    .empty { margin-top: 32px; text-align: center; }
    .loading-center { display: flex; justify-content: center; padding: 40px; }
  `]
})
export class SearchComponent implements OnInit, OnDestroy {
  readonly types: SearchType[] = ['all', 'people', 'posts', 'groups', 'pages', 'listings', 'videos'];
  query = '';
  type: SearchType = 'all';
  data: SearchResponse | null = null;
  loading = false;
  error = '';
  private sub?: Subscription;

  constructor(private route: ActivatedRoute, private router: Router, private api: ApiService) {}

  ngOnInit(): void {
    this.sub = this.route.queryParamMap
      .pipe(
        switchMap((params) => {
          this.query = (params.get('q') ?? '').trim();
          this.type = (params.get('type') as SearchType) || 'all';
          this.error = '';
          if (this.query.length < 2) {
            this.data = null;
            this.error = 'Type at least 2 characters to search.';
            return of(null);
          }
          this.loading = true;
          return this.api.search(this.query, this.type).pipe(catchError(() => {
            this.error = 'Search failed. Please try again.';
            return of(null);
          }));
        })
      )
      .subscribe((res) => {
        this.loading = false;
        this.data = res;
      });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  get isEmpty(): boolean {
    return !!this.data && Object.values(this.data.results).every((list) => !list?.length);
  }

  setType(type: SearchType): void {
    this.router.navigate([], { queryParams: { q: this.query, type }, queryParamsHandling: 'merge' });
  }
}
