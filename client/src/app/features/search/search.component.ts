import { Component, OnDestroy, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { BehaviorSubject, Subscription, combineLatest, switchMap, of, catchError, forkJoin } from 'rxjs';
import { ApiService } from '../../core/services/api.service';
import { AskResponse, SearchResponse, SearchType, SemanticSearchResponse, SemanticType } from '../../models/search.model';
import { PostCardComponent } from '../../shared/components/post-card/post-card.component';
import { EmptyStateComponent, ErrorStateComponent, SkeletonComponent } from '../../shared/components/states';

@Component({
    selector: 'app-search',
    imports: [CommonModule, RouterLink, MatButtonModule, MatButtonToggleModule, MatIconModule, MatProgressSpinnerModule,
      PostCardComponent, EmptyStateComponent, ErrorStateComponent, SkeletonComponent],
    template: `
    <div class="search-page">
      <h1>Results for “{{ query }}”</h1>
      <p class="text-secondary text-sm understood" *ngIf="semantic?.understood_as as u">
        Searching for <strong>{{ u.query }}</strong>
        <span *ngIf="u.since_days"> · last {{ u.since_days }} days</span>
        <span *ngIf="u.author"> · by {{ u.author }}</span>
      </p>
      <mat-button-toggle-group [value]="type" (change)="setType($event.value)" class="tabs" aria-label="Result type">
        <mat-button-toggle *ngFor="let t of types" [value]="t">{{ t | titlecase }}</mat-button-toggle>
      </mat-button-toggle-group>

      <section class="ask card" *ngIf="type === 'all' && query.length >= 3" aria-live="polite">
        <div class="ask-head">
          <mat-icon>auto_awesome</mat-icon>
          <div class="grow">
            <div class="font-semibold">Ask Andromeda</div>
            <div class="text-secondary text-sm">An answer built only from posts, groups and listings you can see.</div>
          </div>
          <button mat-stroked-button (click)="runAsk()" [disabled]="asking" *ngIf="!answer">Ask</button>
        </div>
        <mat-spinner diameter="24" *ngIf="asking"></mat-spinner>
        <div *ngIf="answer" class="answer">
          <p [class.text-secondary]="answer.abstain">{{ answer.answer }}</p>
          <ul *ngIf="answer.claims.length">
            <li *ngFor="let c of answer.claims">
              {{ c.text }}
              <a *ngFor="let s of c.sources; let i = index" [routerLink]="s.url" class="cite" [attr.aria-label]="'Source: ' + s.title">[{{ sourceIndex(s.url) }}]</a>
            </li>
          </ul>
          <ol class="sources text-sm" *ngIf="answer.sources.length && !answer.abstain">
            <li *ngFor="let s of answer.sources"><a [routerLink]="s.url">{{ s.title }}</a><span class="text-secondary" *ngIf="s.author"> · {{ s.author }}</span></li>
          </ol>
          <p class="text-secondary text-sm">AI answers can be wrong. Check the sources.</p>
        </div>
        <p class="text-secondary text-sm" *ngIf="askError">{{ askError }}</p>
      </section>

      <app-skeleton *ngIf="loading" variant="list" [count]="5"></app-skeleton>

      <ng-container *ngIf="!loading">
        <section *ngIf="data?.results?.people?.length">
          <h2>People</h2>
          <a class="row card" *ngFor="let u of data!.results.people" [routerLink]="'/profile/' + u.username">
            <img [src]="u.avatar_url || 'assets/default-avatar.png'" class="avatar md" alt="" />
            <div><div class="font-semibold">{{ u.full_name }}</div><div class="text-secondary text-sm">&#64;{{ u.username }}</div></div>
          </a>
        </section>

        <!-- Ranked hybrid results (lexical + semantic), when available -->
        <section *ngIf="semantic?.results?.length">
          <h2 *ngIf="type === 'all'">Top results</h2>
          <ng-container *ngFor="let hit of semantic!.results">
            <app-post-card *ngIf="hit.type === 'posts'" [post]="hit.item"></app-post-card>
            <a class="row card" *ngIf="hit.type === 'groups'" [routerLink]="'/groups/' + hit.item.id">
              <mat-icon>groups</mat-icon>
              <div><div class="font-semibold">{{ hit.item.name }}</div><div class="text-secondary text-sm">Group · {{ hit.item.members_count }} members</div></div>
            </a>
            <a class="row card" *ngIf="hit.type === 'pages'" [routerLink]="'/pages/' + hit.item.id">
              <mat-icon>flag</mat-icon>
              <div><div class="font-semibold">{{ hit.item.name }}</div><div class="text-secondary text-sm">Page · {{ hit.item.followers_count }} followers</div></div>
            </a>
            <a class="row card" *ngIf="hit.type === 'listings'" [routerLink]="'/marketplace/' + hit.item.id">
              <mat-icon>storefront</mat-icon>
              <div><div class="font-semibold">{{ hit.item.title }}</div><div class="text-secondary text-sm">For sale · {{ hit.item.currency }} {{ hit.item.price }}</div></div>
            </a>
            <a class="row card" *ngIf="hit.type === 'videos'" [routerLink]="'/watch/' + hit.item.id">
              <mat-icon>smart_display</mat-icon>
              <div class="font-semibold">{{ hit.item.title }}</div>
            </a>
          </ng-container>
        </section>

        <!-- Lexical fallback when the semantic endpoint is unavailable -->
        <ng-container *ngIf="!semantic && data">
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
            <a class="row card" *ngFor="let p of data.results.pages" [routerLink]="'/pages/' + p.id">
              <mat-icon>flag</mat-icon>
              <div><div class="font-semibold">{{ p.name }}</div><div class="text-secondary text-sm">{{ p.followers_count }} followers</div></div>
            </a>
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
        </ng-container>

        <app-empty-state *ngIf="isEmpty && !error && !hint" icon="search_off" [title]="'Nothing matched “' + query + '”'"
                         message="Check the spelling, or try fewer or different words."></app-empty-state>
      </ng-container>
      <app-empty-state *ngIf="hint" icon="search" [title]="hint"></app-empty-state>
      <app-error-state *ngIf="error" [message]="error" (retry)="retry$.next(retry$.value + 1)"></app-error-state>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    .search-page { max-width: 720px; margin: 0 auto; padding: 24px 16px; }
    h1 { font-size: 22px; margin-bottom: 8px; }
    h2 { font-size: 16px; margin: 24px 0 8px; }
    .understood { margin: 0 0 12px; }
    .tabs { flex-wrap: wrap; margin-bottom: 8px; }
    section { display: flex; flex-direction: column; gap: 8px; }
    .row { display: flex; align-items: center; gap: 12px; padding: 12px; color: inherit; text-decoration: none; }
    .empty { margin-top: 32px; text-align: center; }
    .loading-center { display: flex; justify-content: center; padding: 40px; }
    .ask { margin-top: 16px; padding: 16px; gap: 12px; }
    .ask-head { display: flex; align-items: center; gap: 12px; }
    .grow { flex: 1; }
    .answer p { margin: 0 0 8px; line-height: 1.5; }
    .answer ul { margin: 0 0 8px; padding-left: 20px; }
    .cite { margin-left: 4px; font-size: 12px; text-decoration: none; }
    .sources { margin: 0 0 8px; padding-left: 20px; }
  `]
})
export class SearchComponent implements OnInit, OnDestroy {
  readonly types: SearchType[] = ['all', 'people', 'posts', 'groups', 'pages', 'listings', 'videos'];
  query = '';
  type: SearchType = 'all';
  data: SearchResponse | null = null;
  semantic: SemanticSearchResponse | null = null;
  answer: AskResponse | null = null;
  asking = false;
  askError = '';
  loading = false;
  error = '';
  /** Not an error: shown when the query is too short to search. */
  hint = '';
  readonly retry$ = new BehaviorSubject(0);
  private sub?: Subscription;
  private askSub?: Subscription;

  constructor(private route: ActivatedRoute, private router: Router, private api: ApiService) {}

  ngOnInit(): void {
    this.sub = combineLatest([this.route.queryParamMap, this.retry$])
      .pipe(
        switchMap(([params]) => {
          this.query = (params.get('q') ?? '').trim();
          this.type = (params.get('type') as SearchType) || 'all';
          this.error = '';
          this.hint = '';
          this.answer = null;
          this.askError = '';
          this.askSub?.unsubscribe();
          this.asking = false;
          if (this.query.length < 2) {
            this.data = null;
            this.semantic = null;
            this.hint = 'Type at least 2 characters to search.';
            return of(null);
          }
          this.loading = true;
          // People always come from the lexical endpoint; everything else is ranked by hybrid search.
          const lexicalType: SearchType = this.type === 'all' ? 'all' : this.type;
          const wantsSemantic = this.type !== 'people';
          return forkJoin({
            lexical: this.api.search(this.query, lexicalType).pipe(catchError(() => of(null))),
            semantic: wantsSemantic
              ? this.api.semanticSearch(this.query, this.type as SemanticType | 'all').pipe(catchError(() => of(null)))
              : of(null),
          });
        })
      )
      .subscribe((res) => {
        this.loading = false;
        if (!res) {
          return;
        }
        this.data = res.lexical;
        this.semantic = res.semantic;
        if (!res.lexical && !res.semantic) {
          this.error = 'Search failed. Please try again.';
        }
      });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
    this.askSub?.unsubscribe();
  }

  get isEmpty(): boolean {
    const people = this.data?.results.people?.length ?? 0;
    if (this.semantic) {
      return !people && !this.semantic.results.length;
    }
    return !!this.data && Object.values(this.data.results).every((list) => !list?.length);
  }

  runAsk(): void {
    this.asking = true;
    this.askError = '';
    this.askSub = this.api.ask(this.query).subscribe({
      next: (res) => { this.answer = res; this.asking = false; },
      error: (err) => {
        this.asking = false;
        this.askError = err?.status === 429 ? 'You have used your AI allowance for now. Try again later.'
          : 'Ask Andromeda is not available right now.';
      },
    });
  }

  sourceIndex(url: string): number {
    return (this.answer?.sources.findIndex((s) => s.url === url) ?? -1) + 1;
  }

  setType(type: SearchType): void {
    this.router.navigate([], { queryParams: { q: this.query, type }, queryParamsHandling: 'merge' });
  }
}
