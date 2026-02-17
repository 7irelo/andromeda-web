import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, Validators, AbstractControl } from '@angular/forms';
import { RouterLink, Router } from '@angular/router';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { AuthService } from '../../../core/services/auth.service';

function passwordMatchValidator(control: AbstractControl) {
  const p = control.get('password');
  const p2 = control.get('password2');
  if (p && p2 && p.value !== p2.value) {
    p2.setErrors({ mismatch: true });
  }
  return null;
}

@Component({
  selector: 'app-register',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, RouterLink,
    MatInputModule, MatButtonModule, MatIconModule, MatProgressSpinnerModule,
  ],
  templateUrl: './register.component.html',
  styleUrls: ['../login/login.component.scss'],
})
export class RegisterComponent {
  form = this.fb.group({
    first_name: ['', Validators.required],
    last_name: ['', Validators.required],
    username: ['', [Validators.required, Validators.minLength(3)]],
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.minLength(8)]],
    password2: ['', Validators.required],
  }, { validators: passwordMatchValidator });

  loading = false;
  error = '';
  hidePassword = true;

  constructor(
    private fb: FormBuilder,
    private authService: AuthService,
    private router: Router,
  ) {}

  submit(): void {
    if (this.form.invalid) return;
    this.loading = true;
    this.error = '';

    this.authService.register(this.form.value as Parameters<AuthService['register']>[0]).subscribe({
      next: () => this.router.navigate(['/feed']),
      error: (err) => {
        const errors = err.error;
        this.error = Object.values(errors).flat().join(' ');
        this.loading = false;
      },
    });
  }
}
