import { Component, ChangeDetectionStrategy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../core/services/api.service';
import { MyCase } from '../../models/moderation.model';

/** What was removed from the member's account, why, and a one-time appeal. */
@Component({
    selector: 'app-my-decisions',
    imports: [CommonModule, FormsModule, MatButtonModule, MatFormFieldModule, MatIconModule, MatInputModule,
      MatSnackBarModule],
    template: `
    <div class="page">
      <h1>Moderation decisions</h1>
      <p class="text-secondary">Content of yours that was removed for breaking the community guidelines.
        You can ask a person to look at each decision again once.</p>
      <p class="text-secondary" *ngIf="loaded && !cases.length">Nothing has been removed from your account.</p>
      <section class="card item" *ngFor="let c of cases">
        <div class="text-secondary text-sm">{{ c.content_type | titlecase }} · {{ c.created_at | date:'mediumDate' }}
          <span *ngIf="c.categories.length"> · {{ c.categories.join(', ') }}</span></div>
        <blockquote>{{ c.snapshot || '(no text)' }}</blockquote>
        <ng-container *ngIf="c.appeal; else canAppeal">
          <p class="status" [ngSwitch]="c.appeal.status">
            <span *ngSwitchCase="'open'">Appeal sent. A moderator will look at it.</span>
            <span *ngSwitchCase="'restored'">Your appeal was accepted and the content was restored.</span>
            <span *ngSwitchCase="'upheld'">Your appeal was reviewed and the removal stands.</span>
          </p>
        </ng-container>
        <ng-template #canAppeal>
          <mat-form-field appearance="outline" class="w-full">
            <mat-label>Why should we look again? (optional)</mat-label>
            <textarea matInput rows="2" maxlength="1000" [(ngModel)]="messages[c.id]"></textarea>
          </mat-form-field>
          <button mat-stroked-button (click)="appeal(c)">Appeal</button>
        </ng-template>
      </section>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    .page { max-width: 720px; margin: 0 auto; padding: 24px 16px; display: flex; flex-direction: column; gap: 12px; }
    h1 { font-size: 22px; margin: 0; }
    .item { padding: 16px; display: flex; flex-direction: column; gap: 8px; }
    blockquote { margin: 0; padding: 8px 12px; border-left: 3px solid rgba(0,0,0,.2); white-space: pre-wrap; word-break: break-word; }
    .status { margin: 0; font-weight: 500; }
  `]
})
export class MyDecisionsComponent implements OnInit {
  cases: MyCase[] = [];
  messages: Record<number, string> = {};
  loaded = false;

  constructor(private api: ApiService, private snack: MatSnackBar) {}

  ngOnInit(): void {
    this.api.getMyModerationCases().subscribe((rows) => { this.cases = rows; this.loaded = true; });
  }

  appeal(c: MyCase): void {
    this.api.appealModeration(c.id, (this.messages[c.id] ?? '').trim()).subscribe({
      next: () => (c.appeal = { id: 0, message: this.messages[c.id] ?? '', status: 'open',
                                created_at: new Date().toISOString(), decided_at: null }),
      error: (err) => this.snack.open(err?.error?.detail ?? 'Could not send the appeal', 'Dismiss', { duration: 4000 }),
    });
  }
}
