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
    <div class="join-page">
      <div class="loading-center" *ngIf="loading"><mat-spinner diameter="40"></mat-spinner></div>

      <div class="card join-card" *ngIf="preview as p">
        <img class="cover" [src]="p.group.cover_photo || 'assets/default-cover.png'" alt="" />
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
        <mat-icon>link_off</mat-icon>
        <p>{{ error }}</p>
        <a mat-stroked-button routerLink="/groups">Browse groups</a>
      </div>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    .join-page { max-width: 560px; margin: 0 auto; padding: 24px 16px; }
    .join-card { overflow: hidden; padding: 0; }
    .cover { width: 100%; height: 160px; object-fit: cover; display: block; }
    .body { padding: 20px 24px; display: flex; flex-direction: column; gap: 6px; }
    .body h1 { font-size: 24px; font-weight: 800; }
    .description { margin-top: 8px; line-height: 1.6; }
    .rules { margin-top: 12px; }
    .rules h3 { font-size: 15px; font-weight: 700; margin-bottom: 6px; }
    .rules ol { padding-left: 20px; display: flex; flex-direction: column; gap: 6px; }
    .rules p { color: var(--text-secondary); }
    .actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
    .error-card { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 32px; text-align: center; }
    .error-card mat-icon { font-size: 40px; width: 40px; height: 40px; opacity: .5; }
    .loading-center { display: flex; justify-content: center; padding: 60px; }
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
