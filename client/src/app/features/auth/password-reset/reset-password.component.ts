import { Component, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { AuthService } from '../../../core/services/auth.service';

@Component({
    selector: 'app-reset-password',
    imports: [CommonModule, ReactiveFormsModule, RouterLink, MatSnackBarModule],
    template: `
    <div class="auth-page">
      <div class="stars" aria-hidden="true"></div>
      <div class="planet" aria-hidden="true"></div>

      <header class="auth-header">
        <a class="brand brand-link" routerLink="/">
          <svg class="brand-mark" viewBox="0 0 32 28" width="30" height="26" aria-hidden="true">
            <defs>
              <linearGradient id="brand-gradient" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stop-color="#ffffff" />
                <stop offset="1" stop-color="#7c8cff" />
              </linearGradient>
            </defs>
            <path d="M16 0 32 28H24.5L16 12.6 9.6 24 20 24 22.2 28H0L16 0Z" />
          </svg>
          ANDROMEDA
        </a>
      </header>

      <div class="auth-main single">
        <section class="auth-card">
          <h1 i18n="@@reset.title">Choose a new password</h1>
          <p class="form-error" *ngIf="!uid || !token" i18n="@@reset.incomplete">This reset link is incomplete. Request a new one.</p>
          <form [formGroup]="form" (ngSubmit)="submit()" *ngIf="uid && token" novalidate>
            <div class="field">
              <label for="reset-password" i18n="@@reset.newPassword">New password</label>
              <input id="reset-password" type="password" autocomplete="new-password" formControlName="password"
                     [attr.aria-invalid]="showPasswordError"
                     [attr.aria-describedby]="showPasswordError ? 'reset-password-error' : null" />
              <p class="field-error" id="reset-password-error" *ngIf="showPasswordError" i18n="@@reset.min">At least 10 characters</p>
            </div>
            <div class="field">
              <label for="reset-confirm" i18n="@@reset.confirm">Confirm new password</label>
              <input id="reset-confirm" type="password" autocomplete="new-password" formControlName="confirm"
                     [attr.aria-invalid]="mismatch || (form.controls.confirm.invalid && form.controls.confirm.touched)"
                     [attr.aria-describedby]="mismatch ? 'reset-confirm-error' : null" />
              <p class="field-error" id="reset-confirm-error" *ngIf="mismatch" i18n="@@reset.mismatch">Passwords don't match.</p>
            </div>
            <div class="form-error" *ngIf="error" role="alert">{{ error }}</div>
            <button class="submit-btn" type="submit" [disabled]="form.invalid || loading">
              @if (loading) { <span i18n="@@common.saving">Saving...</span> } @else { <span i18n="@@reset.update">Update password</span> }
            </button>
          </form>
          <p class="auth-footnote"><a routerLink="/forgot-password" i18n="@@reset.requestNew">Request a new link</a></p>
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
export class ResetPasswordComponent implements OnInit {
  form = this.fb.group({
    password: ['', [Validators.required, Validators.minLength(10)]],
    confirm: ['', Validators.required],
  });
  uid = '';
  token = '';
  loading = false;
  error = '';

  constructor(
    private fb: FormBuilder,
    private route: ActivatedRoute,
    private router: Router,
    private auth: AuthService,
    private snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void {
    const params = this.route.snapshot.queryParamMap;
    this.uid = params.get('uid') ?? '';
    this.token = params.get('token') ?? '';
    // Drop the token from the address bar and browser history.
    this.router.navigate([], { queryParams: {}, replaceUrl: true });
  }

  get showPasswordError(): boolean {
    const password = this.form.controls.password;
    return password.invalid && password.touched;
  }

  get mismatch(): boolean {
    const { password, confirm } = this.form.value;
    return !!confirm && password !== confirm;
  }

  submit(): void {
    if (this.form.invalid || this.mismatch) return;
    this.loading = true;
    this.error = '';
    this.auth.confirmPasswordReset(this.uid, this.token, this.form.value.password as string).subscribe({
      next: () => {
        this.auth.clearSession();
        this.snackBar.open($localize`:@@reset.done:Password updated. Please sign in.`, $localize`:@@common.dismiss:Dismiss`, { duration: 4000 });
        this.router.navigate(['/login']);
      },
      error: (err) => {
        this.loading = false;
        const e = err?.error ?? {};
        this.error = e.new_password?.[0] ?? e.detail ?? $localize`:@@reset.failed:Could not reset the password.`;
      },
    });
  }
}
