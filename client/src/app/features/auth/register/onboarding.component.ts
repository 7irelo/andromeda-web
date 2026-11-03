import { ChangeDetectionStrategy, Component, LOCALE_ID, computed, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { forkJoin, of, catchError, map } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../../core/services/api.service';
import { Group } from '../../../models/group.model';
import { EmptyStateComponent, ErrorStateComponent, SkeletonComponent } from '../../../shared/components/states';

export interface Interest {
  key: string;
  label: string;
  icon: string;
  /** Group-name search used to suggest communities (the API matches on name). */
  search: string;
}

export const INTERESTS: Interest[] = [
  { key: 'music', label: $localize`:@@onboarding.interest.music:Music`, icon: 'music_note', search: 'music' },
  { key: 'sport', label: $localize`:@@onboarding.interest.sport:Sport`, icon: 'sports_soccer', search: 'sport' },
  { key: 'tech', label: $localize`:@@onboarding.interest.tech:Tech`, icon: 'devices', search: 'tech' },
  { key: 'food', label: $localize`:@@onboarding.interest.food:Food`, icon: 'restaurant', search: 'food' },
  { key: 'travel', label: $localize`:@@onboarding.interest.travel:Travel`, icon: 'flight', search: 'travel' },
  { key: 'gaming', label: $localize`:@@onboarding.interest.gaming:Gaming`, icon: 'sports_esports', search: 'gam' },
  { key: 'art', label: $localize`:@@onboarding.interest.art:Art`, icon: 'palette', search: 'art' },
  { key: 'books', label: $localize`:@@onboarding.interest.books:Books`, icon: 'menu_book', search: 'book' },
  { key: 'fitness', label: $localize`:@@onboarding.interest.fitness:Fitness`, icon: 'fitness_center', search: 'fit' },
  { key: 'film', label: $localize`:@@onboarding.interest.film:Film & TV`, icon: 'movie', search: 'film' },
  { key: 'business', label: $localize`:@@onboarding.interest.business:Business`, icon: 'work', search: 'business' },
  { key: 'nature', label: $localize`:@@onboarding.interest.nature:Outdoors`, icon: 'park', search: 'hik' },
];

const MAX_SUGGESTED_GROUPS = 8;

/**
 * The last three sign-up steps: pick interests, join suggested groups, write a first post.
 *
 * The profile has no interests field (PATCH /api/auth/me/ would ignore it), so the
 * choices are not stored: they only seed the group search and the first-post draft.
 */
@Component({
  selector: 'app-onboarding',
  imports: [
    FormsModule, MatIconModule, MatProgressSpinnerModule,
    EmptyStateComponent, ErrorStateComponent, SkeletonComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @switch (step()) {
      @case ('interests') {
        <h2 i18n="@@onboarding.interestsTitle">What are you into?</h2>
        <p class="hint" i18n="@@onboarding.interestsHint">Pick a few and we'll suggest groups to join.</p>

        <div class="chips" role="group" aria-label="Interests" i18n-aria-label="@@onboarding.interestsGroup">
          @for (i of interests; track i.key) {
            <button type="button" class="chip" [class.selected]="selected().has(i.key)"
                    [attr.aria-pressed]="selected().has(i.key)" (click)="toggle(i.key)">
              <mat-icon aria-hidden="true">{{ selected().has(i.key) ? 'check' : i.icon }}</mat-icon>
              {{ i.label }}
            </button>
          }
        </div>

        <div class="step-actions">
          <button class="ghost-btn" type="button" (click)="goGroups()" i18n="@@onboarding.skip">Skip</button>
          <button class="submit-btn" type="button" (click)="goGroups()" [disabled]="!selected().size"
                  i18n="@@onboarding.continue">Continue</button>
        </div>
      }

      @case ('groups') {
        <h2 i18n="@@onboarding.groupsTitle">Join some groups</h2>
        <p class="hint" i18n="@@onboarding.groupsHint">Their posts show up in your feed.</p>

        <div class="group-list">
          @if (groupsLoading()) {
            <app-skeleton variant="list" [count]="4"></app-skeleton>
          } @else if (groupsError()) {
            <app-error-state [compact]="true" (retry)="loadGroups()"></app-error-state>
          } @else if (!groups().length) {
            <app-empty-state [compact]="true" icon="group_add" title="No groups yet"
                             i18n-title="@@onboarding.noGroups"
                             message="You can start one later from the Groups page."
                             i18n-message="@@onboarding.noGroupsHint"></app-empty-state>
          } @else {
            @for (g of groups(); track g.id) {
              <div class="group-row">
                <img [src]="g.cover_photo || 'assets/default-cover.png'" alt="" class="group-thumb" width="44" height="44" />
                <div class="group-info">
                  <div class="group-name">{{ g.name }}</div>
                  <div class="group-meta" i18n="@@onboarding.members">{{ g.members_count }} members</div>
                </div>
                @if (joined().has(g.id)) {
                  <span class="joined" role="status">
                    <mat-icon aria-hidden="true">check</mat-icon>
                    {{ joined().get(g.id) === 'request_pending' ? requestedLabel : joinedLabel }}
                  </span>
                } @else {
                  <button class="ghost-btn" type="button" (click)="join(g)" [disabled]="joining().has(g.id)"
                          [attr.aria-label]="joinLabel(g)">
                    {{ g.privacy === 'public' ? joinText : requestText }}
                  </button>
                }
              </div>
            }
          }
        </div>

        <div class="step-actions">
          <button class="ghost-btn" type="button" (click)="step.set('interests')" i18n="@@onboarding.back">Back</button>
          <button class="submit-btn" type="button" (click)="goPost()" i18n="@@onboarding.continue">Continue</button>
        </div>
      }

      @case ('post') {
        <h2 i18n="@@onboarding.postTitle">Say hello</h2>
        <p class="hint" i18n="@@onboarding.postHint">Write your first post so friends know you're here.</p>

        <div class="field">
          <label for="onboarding-post" i18n="@@onboarding.postLabel">Your first post</label>
          <textarea id="onboarding-post" rows="5" maxlength="5000" [(ngModel)]="draft" name="draft"></textarea>
        </div>
        @if (postError()) {
          <div class="form-error" role="alert">{{ postError() }}</div>
        }

        <div class="step-actions">
          <button class="ghost-btn" type="button" (click)="done.emit()" i18n="@@onboarding.later">Maybe later</button>
          <button class="submit-btn" type="button" (click)="publish()" [disabled]="!draft.trim() || posting()">
            @if (posting()) { <mat-spinner diameter="18" aria-hidden="true"></mat-spinner> }
            <span i18n="@@onboarding.publish">Post and finish</span>
          </button>
        </div>
      }
    }
  `,
  styleUrls: ['../login/login.component.scss', './onboarding.component.scss'],
})
export class OnboardingComponent {
  /** Used to personalise the first-post draft. */
  readonly firstName = input('');
  readonly done = output<void>();

  private readonly api = inject(ApiService);
  private readonly locale = inject(LOCALE_ID);

  readonly interests = INTERESTS;
  readonly step = signal<'interests' | 'groups' | 'post'>('interests');
  readonly selected = signal(new Set<string>());
  readonly groups = signal<Group[]>([]);
  readonly groupsLoading = signal(false);
  readonly groupsError = signal(false);
  readonly joining = signal(new Set<number>());
  readonly joined = signal(new Map<number, string>());
  readonly posting = signal(false);
  readonly postError = signal('');
  draft = '';

  readonly joinText = $localize`:@@onboarding.join:Join`;
  readonly requestText = $localize`:@@onboarding.request:Request`;
  readonly joinedLabel = $localize`:@@onboarding.joined:Joined`;
  readonly requestedLabel = $localize`:@@onboarding.requested:Requested`;

  private readonly chosen = computed(() => this.interests.filter((i) => this.selected().has(i.key)));

  toggle(key: string): void {
    const next = new Set(this.selected());
    if (next.has(key)) next.delete(key);
    else next.add(key);
    this.selected.set(next);
  }

  joinLabel(g: Group): string {
    return g.privacy === 'public'
      ? $localize`:@@onboarding.joinGroup:Join ${g.name}:name:`
      : $localize`:@@onboarding.requestGroup:Request to join ${g.name}:name:`;
  }

  goGroups(): void {
    this.step.set('groups');
    this.loadGroups();
  }

  goPost(): void {
    if (!this.draft) this.draft = this.firstPostDraft();
    this.step.set('post');
  }

  /** One name search per chosen interest (the groups API filters by name), merged; else popular groups. */
  loadGroups(): void {
    this.groupsLoading.set(true);
    this.groupsError.set(false);
    const searches = this.chosen().slice(0, 4).map((i) =>
      this.api.getGroups({ search: i.search }).pipe(map((r) => r.results), catchError(() => of(null))));
    const source = searches.length ? forkJoin(searches) : of([] as (Group[] | null)[]);
    source.subscribe((lists) => {
      const seen = new Set<number>();
      const merged: Group[] = [];
      for (const g of lists.flatMap((l) => l ?? [])) {
        if (seen.has(g.id) || g.is_member || g.privacy === 'secret') continue;
        seen.add(g.id);
        merged.push(g);
      }
      if (merged.length || (searches.length && lists.every((l) => l === null))) {
        this.groupsError.set(searches.length > 0 && lists.every((l) => l === null));
        this.groups.set(merged.slice(0, MAX_SUGGESTED_GROUPS));
        this.groupsLoading.set(false);
        return;
      }
      // Nothing matched the interests: fall back to any groups open to join.
      this.api.getGroups().subscribe({
        next: (r) => {
          this.groups.set(r.results.filter((g) => !g.is_member && g.privacy !== 'secret').slice(0, MAX_SUGGESTED_GROUPS));
          this.groupsLoading.set(false);
        },
        error: () => {
          this.groupsError.set(true);
          this.groupsLoading.set(false);
        },
      });
    });
  }

  join(g: Group): void {
    this.joining.set(new Set(this.joining()).add(g.id));
    this.api.joinGroup(g.id).subscribe({
      next: (res) => {
        this.joined.set(new Map(this.joined()).set(g.id, res.status));
        this.clearJoining(g.id);
      },
      error: () => this.clearJoining(g.id),
    });
  }

  publish(): void {
    const content = this.draft.trim();
    if (!content || this.posting()) return;
    this.posting.set(true);
    this.postError.set('');
    const data = new FormData();
    data.append('content', content);
    data.append('post_type', 'text');
    this.api.createPost(data).subscribe({
      next: () => {
        this.posting.set(false);
        this.done.emit();
      },
      error: (err: HttpErrorResponse) => {
        this.posting.set(false);
        const detail = typeof err.error?.detail === 'string' ? err.error.detail : '';
        this.postError.set(detail || $localize`:@@onboarding.postFailed:Your post could not be published. Try again, or skip for now.`);
      },
    });
  }

  private clearJoining(id: number): void {
    const next = new Set(this.joining());
    next.delete(id);
    this.joining.set(next);
  }

  firstPostDraft(): string {
    const labels = this.chosen().map((i) => i.label.toLowerCase());
    const name = this.firstName();
    if (!labels.length) {
      return name
        ? $localize`:@@onboarding.draftPlain:Hi everyone, ${name}:name: here! I just joined Andromeda.`
        : $localize`:@@onboarding.draftAnon:Hi everyone! I just joined Andromeda.`;
    }
    // "music, food and travel" in the page's language (CLDR list patterns).
    let list = labels.join(', ');
    try {
      list = new Intl.ListFormat(this.locale, { style: 'long', type: 'conjunction' }).format(labels);
    } catch { /* older browser: plain comma list */ }
    return $localize`:@@onboarding.draftInterests:Hi everyone! I just joined Andromeda. I'm into ${list}:interests: — say hi if you are too.`;
  }
}
