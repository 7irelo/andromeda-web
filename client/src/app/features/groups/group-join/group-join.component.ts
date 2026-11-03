import { Component, Input, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../../core/services/api.service';
import { GroupInvitePreview } from '../../../models/group.model';

/** `/groups/join/:token`: preview the group behind an invite link, show its rules, then join. */
@Component({
    selector: 'app-group-join',
    imports: [CommonModule, RouterLink, MatButtonModule, MatIconModule, MatProgressSpinnerModule],
    template: `
    <div class="join-page ui-controls">
      <div class="state-center" *ngIf="loading"><mat-spinner diameter="40"></mat-spinner></div>

      <div class="card join-card" *ngIf="preview as p">
        <div class="item-cover"><img *ngIf="p.group.cover_photo" [src]="p.group.cover_photo" alt="" /></div>
        <div class="body">
          <p class="text-secondary text-sm">You've been invited to join</p>
          <h1>{{ p.group.name }}</h1>
          <p class="text-secondary text-sm">{{ p.group.members_count | number }} members · {{ p.group.privacy | titlecase }}</p>
          <p class="description" *ngIf="p.group.description">{{ p.group.description }}</p>

          <div class="rules" *ngIf="p.group.rules.length > 0">
            <h3>Group rules</h3>
            <ol>
              <li *ngFor="let r of p.group.rules"><strong>{{ r.title }}</strong><p *ngIf="r.description">{{ r.description }}</p></li>
            </ol>
          </div>

          <div class="actions">
            <a mat-flat-button color="primary" *ngIf="p.is_member" [routerLink]="'/groups/' + p.group.id">Open group</a>
            <ng-container *ngIf="!p.is_member">
              <a mat-stroked-button routerLink="/groups">Not now</a>
              <button mat-flat-button color="primary" (click)="accept()" [disabled]="joining">
                {{ p.group.rules.length > 0 ? 'Agree and join' : 'Join group' }}
              </button>
            </ng-container>
          </div>
        </div>
      </div>

      <div class="card error-card" *ngIf="error">
        <mat-icon aria-hidden="true">link_off</mat-icon>
        <p>{{ error }}</p>
        <a mat-stroked-button routerLink="/groups">Browse groups</a>
      </div>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styleUrls: ['../../../shared/styles/ui-controls.scss', '../../../shared/styles/ui-cards.scss'],
    styles: [`
    .join-page { max-width: 520px; margin: 0 auto; padding: var(--space-6) var(--space-4); }
    .join-card { overflow: hidden; }
    .body { display: flex; flex-direction: column; gap: var(--space-1); padding: var(--space-5); font-size: 14px; }
    .body p { margin: 0; }
    .body h1 { margin: 0; font-size: 20px; line-height: 28px; font-weight: 600; letter-spacing: -.01em; overflow-wrap: anywhere; }
    .description { margin-top: var(--space-2) !important; }
    .rules { margin-top: var(--space-3); padding-top: var(--space-3); border-top: 1px solid var(--border); }
    .rules h3 { margin: 0 0 var(--space-2); font-size: 14px; line-height: 20px; font-weight: 600; }
    .rules ol { display: flex; flex-direction: column; gap: var(--space-2); margin: 0; padding-left: var(--space-5); font-size: 13px; }
    .rules p { color: var(--text-secondary); }
    .actions { display: flex; justify-content: flex-end; flex-wrap: wrap; gap: var(--space-2); margin-top: var(--space-4); }
    .error-card { display: flex; flex-direction: column; align-items: center; gap: var(--space-3); padding: var(--space-8); text-align: center; font-size: 14px; }
    .error-card p { margin: 0; }
    .error-card mat-icon { width: 32px; height: 32px; font-size: 32px; color: var(--text-muted); }
  `]
})
export class GroupJoinComponent implements OnInit {
  @Input() token!: string;
  preview: GroupInvitePreview | null = null;
  loading = false;
  joining = false;
  error: string | null = null;

  constructor(private apiService: ApiService, private router: Router) {}

  ngOnInit(): void {
    this.loading = true;
    this.apiService.previewGroupInvite(this.token).subscribe({
      next: (p) => {
        this.preview = p;
        this.loading = false;
      },
      error: (err) => {
        this.loading = false;
        this.error = this.messageFor(err);
      },
    });
  }

  accept(): void {
    if (this.joining) return;
    this.joining = true;
    this.apiService.acceptGroupInvite(this.token).subscribe({
      next: (res) => this.router.navigate(['/groups', res.group_id]),
      error: (err) => {
        this.joining = false;
        this.preview = null;
        this.error = this.messageFor(err);
      },
    });
  }

  private messageFor(err: { status?: number; error?: { detail?: string } }): string {
    if (err?.status === 429) return 'Too many attempts. Wait a minute and try again.';
    return err?.error?.detail ?? 'This invite link is invalid or has expired.';
  }
}
