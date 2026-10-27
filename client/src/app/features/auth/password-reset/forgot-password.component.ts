import { Component, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { AuthService } from '../../../core/services/auth.service';

@Component({
    selector: 'app-forgot-password',
    imports: [CommonModule, ReactiveFormsModule, RouterLink, MatInputModule, MatButtonModule, MatIconModule],
    template: `
    <div class="auth-shell">
      <div class="auth-card card">
        <h1>Reset your password</h1>
        <ng-container *ngIf="!sent; else done">
          <p class="text-secondary">Enter the email on your account and we'll send you a reset link.</p>
          <form [formGroup]="form" (ngSubmit)="submit()">
            <mat-form-field appearance="outline" class="w-full">
              <mat-label>Email</mat-label>
              <input matInput type="email" autocomplete="email" formControlName="email" />
            </mat-form-field>
            <button mat-flat-button color="primary" class="w-full" type="submit" [disabled]="form.invalid || loading">
              {{ loading ? 'Sending...' : 'Send reset link' }}
            </button>
          </form>
        </ng-container>
        <ng-template #done>
          <p><mat-icon class="ok">mark_email_read</mat-icon></p>
          <p>If that email is registered, a reset link is on its way. It expires in one hour.</p>
        </ng-template>
        <p class="back"><a routerLink="/login">Back to sign in</a></p>
      </div>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styleUrls: ['./password-reset.scss']
})
export class ForgotPasswordComponent {
  form = this.fb.group({ email: ['', [Validators.required, Validators.email]] });
  loading = false;
  sent = false;

  constructor(private fb: FormBuilder, private auth: AuthService) {}

  submit(): void {
    if (this.form.invalid) return;
    this.loading = true;
    // The API answers the same way whether or not the account exists.
    this.auth.requestPasswordReset(this.form.value.email as string).subscribe({
      next: () => (this.sent = true),
      error: () => (this.sent = true),
      complete: () => (this.loading = false),
    });
  }
}
