import { Component, EventEmitter, Input, OnInit, Output, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, FormGroup, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../../core/services/api.service';
import { AuthService } from '../../../core/services/auth.service';
import { Page, PAGE_CATEGORIES, PageRole, PageTeamMember } from '../../../models/page.model';
import { User } from '../../../models/user.model';

/**
 * Page team tools. Admins edit the page and manage roles; editors and analysts
 * see the team and can leave it. The server enforces all of this.
 */
@Component({
    selector: 'app-page-manage',
    imports: [
        CommonModule, FormsModule, ReactiveFormsModule, MatButtonModule, MatFormFieldModule, MatIconModule,
        MatInputModule, MatSelectModule, MatSnackBarModule,
    ],
    template: `
    <!-- Edit (admins) -->
    <div class="card section" *ngIf="isAdmin" [formGroup]="form">
      <h3>Edit page</h3>
      <div class="images">
        <div class="image-pick">
          <img class="avatar-preview" [src]="avatarPreview || page.avatar || 'assets/default-avatar.png'" alt="Avatar preview" />
          <button mat-stroked-button type="button" (click)="avatarInput.click()">Change picture</button>
          <input #avatarInput type="file" accept="image/jpeg,image/png,image/webp,image/gif" hidden (change)="onImage($event, 'avatar')" />
        </div>
        <div class="image-pick">
          <img *ngIf="coverPreview || page.cover_photo as src; else noCover" class="cover-preview" [src]="src" alt="Cover preview" />
          <ng-template #noCover><div class="cover-preview cover-empty"></div></ng-template>
          <button mat-stroked-button type="button" (click)="coverInput.click()">Change cover</button>
          <input #coverInput type="file" accept="image/jpeg,image/png,image/webp,image/gif" hidden (change)="onImage($event, 'cover_photo')" />
        </div>
      </div>
      <mat-form-field appearance="outline" class="w-full">
        <mat-label>Name</mat-label>
        <input matInput formControlName="name" maxlength="255" />
      </mat-form-field>
      <mat-form-field appearance="outline" class="w-full">
        <mat-label>Username</mat-label>
        <input matInput formControlName="username" maxlength="100" />
        <mat-hint>Lowercase letters, numbers, dots, dashes and underscores.</mat-hint>
      </mat-form-field>
      <mat-form-field appearance="outline" class="w-full">
        <mat-label>Category</mat-label>
        <mat-select formControlName="category">
          <mat-option *ngFor="let c of categories" [value]="c.value">{{ c.label }}</mat-option>
        </mat-select>
      </mat-form-field>
      <mat-form-field appearance="outline" class="w-full">
        <mat-label>Description</mat-label>
        <textarea matInput formControlName="description" rows="3" maxlength="5000"></textarea>
      </mat-form-field>
      <mat-form-field appearance="outline" class="w-full">
        <mat-label>Website</mat-label>
        <input matInput formControlName="website" placeholder="https://" />
      </mat-form-field>
      <div class="two-col">
        <mat-form-field appearance="outline">
          <mat-label>Contact email</mat-label>
          <input matInput type="email" formControlName="email" />
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>Phone</mat-label>
          <input matInput formControlName="phone" maxlength="30" />
        </mat-form-field>
      </div>
      <p class="text-secondary text-xs">Verification badges are granted by Andromeda staff.</p>
      <div class="row-actions">
        <button mat-flat-button color="primary" (click)="save()" [disabled]="saving || form.invalid">
          {{ saving ? 'Saving...' : 'Save changes' }}
        </button>
      </div>
    </div>

    <!-- Team -->
    <div class="card section">
      <h3>Page team</h3>
      <div class="team-row" *ngFor="let m of team">
        <img [src]="m.user.avatar_url || 'assets/default-avatar.png'" class="avatar sm" [alt]="m.user.username" />
        <span class="team-name text-sm font-semibold">{{ m.user.full_name }}</span>
        <ng-container *ngIf="isAdmin && m.user.id !== page.created_by?.id; else roleLabel">
          <mat-select class="role-select" aria-label="Role" i18n-aria-label="@@pages.teamRole" [value]="m.role" (selectionChange)="setRole(m.user, $event.value)">
            <mat-option *ngFor="let r of roles" [value]="r">{{ r | titlecase }}</mat-option>
          </mat-select>
        </ng-container>
        <ng-template #roleLabel>
          <span class="text-xs text-secondary">{{ m.user.id === page.created_by?.id ? 'Creator' : (m.role | titlecase) }}</span>
        </ng-template>
        <button mat-icon-button *ngIf="canRemove(m)" (click)="remove(m)"
          [attr.aria-label]="m.user.id === meId ? 'Leave the team' : 'Remove from team'">
          <mat-icon>{{ m.user.id === meId ? 'logout' : 'person_remove' }}</mat-icon>
        </button>
      </div>

      <div class="add-member" *ngIf="isAdmin">
        <mat-form-field appearance="outline" class="grow">
          <mat-label>Add someone by name</mat-label>
          <input matInput [(ngModel)]="query" (keyup.enter)="search()" />
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>Role</mat-label>
          <mat-select [(ngModel)]="newRole">
            <mat-option *ngFor="let r of roles" [value]="r">{{ r | titlecase }}</mat-option>
          </mat-select>
        </mat-form-field>
        <button mat-stroked-button (click)="search()" [disabled]="query.trim().length < 2">Search</button>
      </div>
      <div class="team-row" *ngFor="let u of results">
        <img [src]="u.avatar_url || 'assets/default-avatar.png'" class="avatar sm" [alt]="u.username" />
        <span class="team-name text-sm">{{ u.full_name }} <span class="text-secondary">&#64;{{ u.username }}</span></span>
        <button mat-flat-button color="primary" (click)="setRole(u, newRole)">Add as {{ newRole }}</button>
      </div>
    </div>

    <div class="card section" *ngIf="isAdmin">
      <h3 class="danger-title">Delete page</h3>
      <p class="text-secondary text-sm">This removes the page for everyone and can't be undone.</p>
      <div class="row-actions">
        <button mat-stroked-button class="btn-danger" (click)="deletePage()">Delete page</button>
      </div>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styleUrls: ['../../../shared/styles/ui-controls.scss', '../../../shared/styles/ui-cards.scss'],
    styles: [`
    :host { display: flex; flex-direction: column; gap: var(--space-4); }
    .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3); }
    @media (max-width: 600px) { .two-col { grid-template-columns: 1fr; gap: 0; } }
    .images { display: flex; flex-wrap: wrap; gap: var(--space-6); margin-bottom: var(--space-4); }
    .image-pick { display: flex; flex-direction: column; align-items: flex-start; gap: var(--space-2); }
    .avatar-preview { width: 72px; height: 72px; object-fit: cover; border-radius: var(--radius-lg); }
    .cover-preview { width: 200px; max-width: 100%; height: 72px; object-fit: cover; border-radius: var(--radius-sm); }
    .cover-empty { background: var(--primary-light); }
    .row-actions { display: flex; justify-content: flex-end; flex-wrap: wrap; gap: var(--space-2); margin-top: var(--space-2); }
    .team-row { display: flex; align-items: center; flex-wrap: wrap; gap: var(--space-3); min-height: var(--touch-target); padding: var(--space-1) 0; }
    .team-name { flex: 1 1 120px; min-width: 0; overflow-wrap: anywhere; }
    .role-select {
      display: flex; align-items: center; width: 120px; min-height: 36px; padding: 0 10px;
      border: 1px solid var(--border-strong); border-radius: var(--radius-sm); font-size: 13px;
    }
    @media (max-width: 600px) { .role-select { min-height: var(--touch-target); } }
    .add-member { display: flex; align-items: flex-start; flex-wrap: wrap; gap: var(--space-2); margin-top: var(--space-3); }
    .add-member button { margin-top: var(--space-1); }
    .grow { flex: 1 1 180px; min-width: 0; }
    .danger-title { color: var(--danger-text); }
  `]
})
export class PageManageComponent implements OnInit {
  @Input({ required: true }) page!: Page;
  @Output() pageChange = new EventEmitter<Page>();
  @Output() deleted = new EventEmitter<void>();

  readonly categories = PAGE_CATEGORIES;
  readonly roles: PageRole[] = ['admin', 'editor', 'analyst'];
  form!: FormGroup;
  saving = false;
  files: Partial<Record<'avatar' | 'cover_photo', File>> = {};
  avatarPreview: string | null = null;
  coverPreview: string | null = null;

  team: PageTeamMember[] = [];
  query = '';
  newRole: PageRole = 'editor';
  results: User[] = [];
  meId: number | null = null;

  constructor(
    private apiService: ApiService,
    private authService: AuthService,
    private fb: FormBuilder,
    private snackBar: MatSnackBar,
  ) {
    this.meId = this.authService.currentUser?.id ?? null;
  }

  get isAdmin(): boolean {
    return this.page.my_role === 'admin';
  }

  ngOnInit(): void {
    this.form = this.fb.group({
      name: [this.page.name, [Validators.required, Validators.maxLength(255)]],
      username: [this.page.username, [Validators.required, Validators.pattern(/^[a-z0-9][a-z0-9._-]{2,99}$/)]],
      category: [this.page.category],
      description: [this.page.description, Validators.maxLength(5000)],
      website: [this.page.website, Validators.pattern(/^(https?:\/\/.+)?$/i)],
      email: [this.page.email, Validators.email],
      phone: [this.page.phone, Validators.maxLength(30)],
    });
    this.loadTeam();
  }

  loadTeam(): void {
    this.apiService.getPageTeam(this.page.id).subscribe({ next: (team) => (this.team = team) });
  }

  onImage(event: Event, field: 'avatar' | 'cover_photo'): void {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    this.files[field] = file;
    const reader = new FileReader();
    reader.onload = () => {
      if (field === 'avatar') this.avatarPreview = reader.result as string;
      else this.coverPreview = reader.result as string;
    };
    reader.readAsDataURL(file);
  }

  save(): void {
    if (this.form.invalid || this.saving) return;
    this.saving = true;
    const data = new FormData();
    Object.entries(this.form.value).forEach(([k, v]) => data.append(k, String(v ?? '')));
    Object.entries(this.files).forEach(([k, f]) => f && data.append(k, f));
    this.apiService.updatePage(this.page.id, data).subscribe({
      next: (p) => {
        this.saving = false;
        this.files = {};
        this.pageChange.emit(p);
        this.toast('Page updated');
      },
      error: (err) => {
        this.saving = false;
        this.toast(this.firstError(err) ?? 'Could not save the page');
      },
    });
  }

  search(): void {
    const q = this.query.trim();
    if (q.length < 2) return;
    this.apiService.searchUsers(encodeURIComponent(q)).subscribe({
      next: (res) => {
        const onTeam = new Set(this.team.map((m) => m.user.id));
        this.results = res.results.filter((u) => !onTeam.has(u.id));
      },
    });
  }

  canRemove(m: PageTeamMember): boolean {
    if (m.user.id === this.page.created_by?.id) return false;
    return this.isAdmin || m.user.id === this.meId;
  }

  setRole(user: Pick<User, 'id'>, role: PageRole): void {
    this.apiService.setPageRole(this.page.id, user.id, role).subscribe({
      next: () => {
        this.results = this.results.filter((u) => u.id !== user.id);
        this.loadTeam();
      },
      error: (err) => {
        this.toast(err?.error?.detail ?? 'Could not change the role');
        this.loadTeam();
      },
    });
  }

  remove(m: PageTeamMember): void {
    const leaving = m.user.id === this.meId;
    if (!confirm(leaving ? 'Leave this page team?' : `Remove ${m.user.full_name} from the page team?`)) return;
    this.apiService.removePageRole(this.page.id, m.user.id).subscribe({
      next: () => {
        this.team = this.team.filter((x) => x.id !== m.id);
        if (leaving) this.pageChange.emit({ ...this.page, my_role: null });
      },
      error: (err) => this.toast(err?.error?.detail ?? 'Could not remove this person'),
    });
  }

  deletePage(): void {
    if (!confirm(`Delete ${this.page.name}? This can't be undone.`)) return;
    this.apiService.deletePage(this.page.id).subscribe({
      next: () => this.deleted.emit(),
      error: () => this.toast('Could not delete the page'),
    });
  }

  private firstError(err: { error?: Record<string, unknown> }): string | null {
    const body = err?.error;
    if (!body || typeof body !== 'object') return null;
    const first = Object.values(body)[0];
    return Array.isArray(first) ? String(first[0]) : typeof first === 'string' ? first : null;
  }

  private toast(message: string): void {
    this.snackBar.open(message, 'Dismiss', { duration: 3000 });
  }
}
