import { Component, ChangeDetectionStrategy, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialog, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
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
    imports: [CommonModule, FormsModule, MatDialogModule, MatButtonModule, MatFormFieldModule, MatInputModule,
      MatRadioModule],
    template: `
    <h2 mat-dialog-title>Report {{ data.label || data.type }}</h2>
    <mat-dialog-content>
      <p class="text-secondary">What's wrong with it? Reports are private: the person won't know who reported them.</p>
      <mat-radio-group [(ngModel)]="reason" class="reasons" aria-label="Reason">
        <mat-radio-button *ngFor="let r of reasons" [value]="r.key">{{ r.label }}</mat-radio-button>
      </mat-radio-group>
      <mat-form-field appearance="outline" class="w-full">
        <mat-label>Anything else we should know? (optional)</mat-label>
        <textarea matInput rows="3" maxlength="1000" [(ngModel)]="details"></textarea>
      </mat-form-field>
      <p class="error-msg" *ngIf="error" role="alert">{{ error }}</p>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Cancel</button>
      <button mat-flat-button color="warn" (click)="send()" [disabled]="!reason || sending">Report</button>
    </mat-dialog-actions>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`.reasons { display: flex; flex-direction: column; gap: 4px; margin-bottom: 16px; }`]
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
