import { Component, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { AuthService } from '../../../core/services/auth.service';

@Component({
    selector: 'app-reset-password',
    imports: [CommonModule, ReactiveFormsModule, RouterLink, MatInputModule, MatButtonModule, MatSnackBarModule],
    template: `
    <div class="auth-shell">
      <div class="auth-card card">
        <h1>Choose a new password</h1>
        <p class="error" *ngIf="!uid || !token">This reset link is incomplete. Request a new one.</p>
        <form [formGroup]="form" (ngSubmit)="submit()" *ngIf="uid && token">
          <mat-form-field appearance="outline" class="w-full">
            <mat-label>New password</mat-label>
            <input matInput type="password" autocomplete="new-password" formControlName="password" />
            <mat-error>At least 10 characters</mat-error>
          </mat-form-field>
          <mat-form-field appearance="outline" class="w-full">
            <mat-label>Confirm new password</mat-label>
            <input matInput type="password" autocomplete="new-password" formControlName="confirm" />
          </mat-form-field>
          <p class="error" *ngIf="mismatch">Passwords don't match.</p>
          <p class="error" *ngIf="error">{{ error }}</p>
          <button mat-flat-button color="primary" class="w-full" type="submit" [disabled]="form.invalid || loading">
            {{ loading ? 'Saving...' : 'Update password' }}
          </button>
        </form>
        <p class="back"><a routerLink="/forgot-password">Request a new link</a></p>
      </div>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styleUrls: ['./password-reset.scss']
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
        this.snackBar.open('Password updated. Please sign in.', 'Dismiss', { duration: 4000 });
        this.router.navigate(['/login']);
      },
      error: (err) => {
        this.loading = false;
        const e = err?.error ?? {};
        this.error = e.new_password?.[0] ?? e.detail ?? 'Could not reset the password.';
      },
    });
  }
}
