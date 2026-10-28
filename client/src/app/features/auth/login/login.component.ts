import { Component, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { ActivatedRoute, RouterLink, Router } from '@angular/router';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { AuthService } from '../../../core/services/auth.service';
import { safeReturnUrl } from '../../../core/guards/auth.guard';

@Component({
    selector: 'app-login',
    imports: [
        CommonModule, ReactiveFormsModule, RouterLink,
        MatInputModule, MatButtonModule, MatIconModule, MatProgressSpinnerModule,
    ],
    templateUrl: './login.component.html',
    changeDetection: ChangeDetectionStrategy.Eager,
    styleUrls: ['./login.component.scss']
})
export class LoginComponent {
  form = this.fb.group({
    username: ['', [Validators.required]],
    password: ['', [Validators.required]],
  });
  codeForm = this.fb.group({ code: ['', [Validators.required, Validators.maxLength(12)]] });
  loading = false;
  error = '';
  hidePassword = true;
  /** Set once the password is accepted and a second factor is needed. */
  mfaToken: string | null = null;

  constructor(
    private fb: FormBuilder,
    private authService: AuthService,
    private router: Router,
    private route: ActivatedRoute,
  ) {}

  private done(): void {
    this.router.navigateByUrl(safeReturnUrl(this.route.snapshot.queryParamMap.get('returnUrl')));
  }

  submit(): void {
    if (this.form.invalid) return;
    this.loading = true;
    this.error = '';

    this.authService.login(this.form.value as { username: string; password: string }).subscribe({
      next: (res) => {
        if ('mfa_required' in res) {
          this.mfaToken = res.mfa_token;
          this.loading = false;
          return;
        }
        this.done();
      },
      error: (err) => {
        this.error = err.error?.detail || 'Invalid credentials. Please try again.';
        this.loading = false;
      },
    });
  }

  submitCode(): void {
    if (this.codeForm.invalid || !this.mfaToken) return;
    this.loading = true;
    this.error = '';
    this.authService.completeMfaLogin(this.mfaToken, (this.codeForm.value.code ?? '').trim()).subscribe({
      next: () => this.done(),
      error: (err) => {
        this.error = err.error?.detail || 'That code did not work. Try again.';
        this.loading = false;
      },
    });
  }

  startOver(): void {
    this.mfaToken = null;
    this.codeForm.reset();
    this.form.get('password')?.reset();
    this.error = '';
  }
}
