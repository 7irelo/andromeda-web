import { Component, ChangeDetectionStrategy, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../core/services/api.service';
import { DataExportEntry } from '../../models/moderation.model';

/** Download a copy of your data, and see moderation decisions about your content. */
@Component({
    selector: 'app-data-settings',
    imports: [CommonModule, RouterLink, MatButtonModule, MatIconModule, MatSnackBarModule],
    template: `
    <section class="settings-section card">
      <h2><mat-icon>folder_zip</mat-icon> Your data</h2>
      <p class="text-secondary">Download everything you have on Andromeda: profile, posts, comments, messages you sent,
        listings, connections, notifications and the files you uploaded. The download is kept for 7 days.</p>
      <div class="row">
        <button mat-stroked-button (click)="request()" [disabled]="pending">
          {{ pending ? 'Preparing your file…' : 'Request a copy' }}
        </button>
      </div>
      <div class="row" *ngFor="let e of ready">
        <mat-icon>description</mat-icon>
        <span class="grow">{{ e.created_at | date:'medium' }} · {{ e.size_bytes / 1048576 | number:'1.0-1' }} MB
          <span class="text-secondary"> · until {{ e.expires_at | date:'mediumDate' }}</span></span>
        <button mat-button (click)="download(e)">Download</button>
      </div>
      <p><a routerLink="/decisions">Moderation decisions about your content</a> ·
        <a routerLink="/privacy">Privacy policy</a> · <a routerLink="/terms">Terms</a></p>
    </section>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    .settings-section { padding: 24px; margin-bottom: 16px; }
    .row { display: flex; align-items: center; gap: 12px; padding: 4px 0; }
    .grow { flex: 1; }
  `]
})
export class DataSettingsComponent implements OnInit, OnDestroy {
  exports: DataExportEntry[] = [];
  private poll: ReturnType<typeof setInterval> | null = null;

  constructor(private api: ApiService, private snack: MatSnackBar) {}

  get pending(): boolean {
    return this.exports.some((e) => e.status === 'pending');
  }

  get ready(): DataExportEntry[] {
    return this.exports.filter((e) => e.status === 'ready' && (!e.expires_at || new Date(e.expires_at) > new Date()));
  }

  ngOnInit(): void {
    this.refresh();
  }

  ngOnDestroy(): void {
    if (this.poll) clearInterval(this.poll);
  }

  private refresh(): void {
    this.api.getDataExports().subscribe((rows) => {
      this.exports = rows;
      if (this.pending && !this.poll) {
        this.poll = setInterval(() => this.refresh(), 5000);
      } else if (!this.pending && this.poll) {
        clearInterval(this.poll);
        this.poll = null;
      }
    });
  }

  request(): void {
    this.api.requestDataExport().subscribe({
      next: () => this.refresh(),
      error: (err) => this.snack.open(err?.status === 429 ? 'You can request two copies a day.'
        : err?.error?.detail ?? 'Could not start the export', 'Dismiss', { duration: 4000 }),
    });
  }

  download(e: DataExportEntry): void {
    // Fetched with the access token (it isn't a public link), then saved from memory.
    this.api.downloadDataExport(e.id).subscribe((blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `andromeda-export-${e.created_at.slice(0, 10)}.zip`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  }
}
