import { Component, ChangeDetectionStrategy, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialog, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatRadioModule } from '@angular/material/radio';
import { MatSnackBar } from '@angular/material/snack-bar';
import { ApiService } from '../../../core/services/api.service';
import { ReportReason, ReportableType } from '../../../models/moderation.model';

export interface ReportDialogData {
  type: ReportableType;
  id: number;
  /** Shown in the title, e.g. "post" or "@thandi". */
  label?: string;
}

/** Report anything the member can see. Open it with `openReportDialog(dialog, {...})`. */
@Component({
    selector: 'app-report-dialog',
    imports: [CommonModule, FormsModule, MatDialogModule, MatButtonModule, MatRadioModule],
    template: `
    <h2 mat-dialog-title>Report {{ data.label || data.type }}</h2>
    <mat-dialog-content>
      <p class="hint">What's wrong with it? Reports are private: the person won't know who reported them.</p>
      <mat-radio-group [(ngModel)]="reason" class="reasons" aria-label="Reason">
        <mat-radio-button *ngFor="let r of reasons" [value]="r.key">{{ r.label }}</mat-radio-button>
      </mat-radio-group>
      <div class="field">
        <label for="report-details">Anything else we should know? (optional)</label>
        <textarea id="report-details" rows="3" maxlength="1000" [(ngModel)]="details"></textarea>
      </div>
      <p class="error-msg" *ngIf="error" role="alert">{{ error }}</p>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Cancel</button>
      <button mat-flat-button (click)="send()" [disabled]="!reason || sending">Report</button>
    </mat-dialog-actions>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    :host { display: block; background: var(--surface); color: var(--text-primary); border-radius: var(--radius-lg);
      --mat-dialog-subhead-size: var(--font-size-lg); --mat-dialog-subhead-weight: 600; --mat-dialog-subhead-color: var(--text-primary);
      --mat-dialog-supporting-text-size: var(--font-size-base); --mat-dialog-supporting-text-color: var(--text-primary);
      --mat-button-text-label-text-color: var(--text-primary); }
    .hint { margin: 0 0 var(--space-3); font-size: var(--font-size-sm); color: var(--text-secondary); }
    .reasons { display: flex; flex-direction: column; gap: 0; margin-bottom: var(--space-3); }
    .field { display: flex; flex-direction: column; gap: var(--space-1); }
    .field label { font-size: var(--font-size-sm); font-weight: 500; color: var(--text-primary); }
    .field textarea { width: 100%; padding: var(--space-2) var(--space-3); font: inherit; font-size: var(--font-size-base);
      color: var(--text-primary); resize: vertical; background: var(--surface); border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm); }
    .field textarea:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 1px var(--primary); }
    .error-msg { margin: var(--space-2) 0 0; font-size: var(--font-size-sm); color: var(--danger-text); }
    @media (max-width: 600px) {
      :host { --mat-button-filled-container-height: 44px; --mat-button-text-container-height: 44px; }
      .field textarea { font-size: 16px; }
    }
  `]
})
export class ReportDialogComponent implements OnInit {
  readonly data = inject<ReportDialogData>(MAT_DIALOG_DATA);
  private readonly ref = inject(MatDialogRef<ReportDialogComponent>);
  private readonly api = inject(ApiService);
  private readonly snack = inject(MatSnackBar);
  reasons: ReportReason[] = [];
  reason = '';
  details = '';
  sending = false;
  error = '';

  ngOnInit(): void {
    this.api.getReportReasons().subscribe((r) => (this.reasons = r.reasons));
  }

  send(): void {
    this.sending = true;
    this.error = '';
    this.api.report(this.data.type, this.data.id, this.reason, this.details.trim()).subscribe({
      next: (r) => {
        this.snack.open(r.detail, 'OK', { duration: 4000 });
        this.ref.close(true);
      },
      error: (err) => {
        this.sending = false;
        this.error = err?.error?.detail ?? 'Could not send the report. Try again.';
      },
    });
  }
}

export function openReportDialog(dialog: MatDialog, data: ReportDialogData) {
  return dialog.open(ReportDialogComponent, { data, width: '440px', maxWidth: '95vw', autoFocus: 'first-tabbable' });
}
