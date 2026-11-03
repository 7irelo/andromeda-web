import { Component, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { AuthService } from '../../../core/services/auth.service';

@Component({
    selector: 'app-forgot-password',
    imports: [CommonModule, ReactiveFormsModule, RouterLink, MatIconModule],
    template: `
    <div class="auth-page">

      <header class="auth-header">
        <a class="brand brand-link" routerLink="/">
          <svg class="brand-mark" viewBox="0 0 32 28" width="30" height="26" aria-hidden="true">
            <path d="M16 0 32 28H24.5L16 12.6 9.6 24 20 24 22.2 28H0L16 0Z" />
          </svg>
          Andromeda
        </a>
      </header>

      <div class="auth-main single">
        <section class="auth-card">
          <h1 i18n="@@reset.forgotTitle">Reset your password</h1>
          <ng-container *ngIf="!sent; else done">
            <p class="auth-hint" i18n="@@reset.forgotHint">Enter the email on your account and we'll send you a reset link.</p>
            <form [formGroup]="form" (ngSubmit)="submit()" novalidate>
              <div class="field">
                <label for="forgot-email" i18n="@@reset.email">Email</label>
                <input id="forgot-email" type="email" autocomplete="email" formControlName="email"
                       [attr.aria-invalid]="showEmailError"
                       [attr.aria-describedby]="showEmailError ? 'forgot-email-error' : null" />
                <p class="field-error" id="forgot-email-error" *ngIf="showEmailError" i18n="@@register.emailInvalid">Valid email required</p>
              </div>
              <button class="submit-btn" type="submit" [disabled]="form.invalid || loading">
                @if (loading) { <span i18n="@@reset.sending">Sending...</span> } @else { <span i18n="@@reset.send">Send reset link</span> }
              </button>
            </form>
          </ng-container>
          <ng-template #done>
            <mat-icon class="notice-icon" aria-hidden="true">mark_email_read</mat-icon>
            <p class="notice" role="status" i18n="@@reset.sent">If that email is registered, a reset link is on its way. It expires in one hour.</p>
          </ng-template>
          <p class="auth-footnote"><a routerLink="/login" i18n="@@reset.backToSignIn">Back to sign in</a></p>
        </section>
      </div>

      <footer class="auth-footer">
        <a routerLink="/privacy" i18n="@@login.privacy">Privacy</a>
        <a routerLink="/terms" i18n="@@login.terms">Terms</a>
      </footer>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styleUrls: ['../login/login.component.scss', './password-reset.scss']
})
export class ForgotPasswordComponent {
  form = this.fb.group({ email: ['', [Validators.required, Validators.email]] });
  loading = false;
  sent = false;

  constructor(private fb: FormBuilder, private auth: AuthService) {}

  get showEmailError(): boolean {
    const email = this.form.controls.email;
    return email.invalid && email.touched;
  }

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
