import { Component, ViewChild, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, Validators, AbstractControl } from '@angular/forms';
import { RouterLink, Router } from '@angular/router';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { AuthService } from '../../../core/services/auth.service';
import { ApiService } from '../../../core/services/api.service';
import { User } from '../../../models/user.model';
import { ImageCropperComponent, ImageCropperResult } from '../../../shared/components/image-cropper/image-cropper.component';

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
    MatSnackBarModule, MatDialogModule,
  ],
  templateUrl: './register.component.html',
  styleUrls: ['../login/login.component.scss', './register.component.scss'],
})
export class RegisterComponent {
  @ViewChild('avatarInput') avatarInput!: ElementRef<HTMLInputElement>;
  @ViewChild('coverInput') coverInput!: ElementRef<HTMLInputElement>;

  currentStep = 1;

  // Step 1: Account
  accountForm = this.fb.group({
    first_name: ['', Validators.required],
    last_name: ['', Validators.required],
    username: ['', [Validators.required, Validators.minLength(3)]],
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.minLength(8)]],
    password2: ['', Validators.required],
  }, { validators: passwordMatchValidator });

  // Step 2: Profile
  profileForm = this.fb.group({
    bio: [''],
    birth_date: [''],
    location: [''],
  });

  // Step 3: Find friends
  suggestions: User[] = [];

  loading = false;
  error = '';
  hidePassword = true;

  avatarPreview: string | null = null;
  coverPreview: string | null = null;
  avatarFile: File | null = null;
  coverFile: File | null = null;
  uploadingAvatar = false;
  uploadingCover = false;

  constructor(
    private fb: FormBuilder,
    private authService: AuthService,
    private apiService: ApiService,
    private router: Router,
    private snackBar: MatSnackBar,
    private dialog: MatDialog,
  ) {}

  submitStep1(): void {
    if (this.accountForm.invalid) return;
    this.loading = true;
    this.error = '';

    this.authService.register(this.accountForm.value as Parameters<AuthService['register']>[0]).subscribe({
      next: () => {
        this.loading = false;
        this.currentStep = 2;
      },
      error: (err) => {
        const errors = err.error;
        this.error = Object.values(errors).flat().join(' ');
        this.loading = false;
      },
    });
  }

  submitStep2(): void {
    this.loading = true;
    const fd = new FormData();
    const vals = this.profileForm.value;
    if (vals.bio) fd.append('bio', vals.bio);
    if (vals.birth_date) fd.append('birth_date', vals.birth_date);
    if (vals.location) fd.append('location', vals.location);
    if (this.avatarFile) fd.append('avatar', this.avatarFile);
    if (this.coverFile) fd.append('cover_photo', this.coverFile);

    this.apiService.updateProfile(fd).subscribe({
      next: () => {
        this.authService.fetchMe().subscribe();
        this.loading = false;
        this.currentStep = 3;
        this.loadSuggestions();
      },
      error: () => {
        this.loading = false;
        this.snackBar.open('Failed to update profile', 'Dismiss', { duration: 3000 });
        // Still advance to step 3
        this.currentStep = 3;
        this.loadSuggestions();
      },
    });
  }

  skipStep2(): void {
    this.currentStep = 3;
    this.loadSuggestions();
  }

  loadSuggestions(): void {
    this.apiService.getSuggestions().subscribe({
      next: (users) => (this.suggestions = users),
      error: () => {},
    });
  }

  sendRequest(user: User): void {
    this.apiService.sendFriendRequest(user.id).subscribe({
      next: () => {
        user.friend_request_sent = true;
        this.snackBar.open('Friend request sent!', 'Dismiss', { duration: 2000 });
      },
      error: () => this.snackBar.open('Could not send request', 'Dismiss', { duration: 3000 }),
    });
  }

  finish(): void {
    this.router.navigate(['/feed']);
  }

  openAvatarPicker(): void { this.avatarInput?.nativeElement.click(); }
  openCoverPicker(): void { this.coverInput?.nativeElement.click(); }

  onAvatarSelected(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    const ref = this.dialog.open(ImageCropperComponent, {
      data: { file, aspectRatio: 1, title: 'Crop Avatar' },
      width: '500px',
    });
    ref.afterClosed().subscribe((result: ImageCropperResult | undefined) => {
      if (result) {
        this.avatarFile = new File([result.blob], 'avatar.jpg', { type: 'image/jpeg' });
        this.avatarPreview = result.dataUrl;
      }
    });
  }

  onCoverSelected(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    const ref = this.dialog.open(ImageCropperComponent, {
      data: { file, aspectRatio: 16 / 9, title: 'Crop Cover Photo' },
      width: '600px',
    });
    ref.afterClosed().subscribe((result: ImageCropperResult | undefined) => {
      if (result) {
        this.coverFile = new File([result.blob], 'cover.jpg', { type: 'image/jpeg' });
        this.coverPreview = result.dataUrl;
      }
    });
  }
}
