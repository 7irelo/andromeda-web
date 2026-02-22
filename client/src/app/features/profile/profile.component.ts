import { Component, Input, OnInit, OnChanges, OnDestroy, ViewChild, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormsModule, FormBuilder, FormGroup } from '@angular/forms';
import { Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTabsModule } from '@angular/material/tabs';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { Subscription } from 'rxjs';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { User } from '../../models/user.model';
import { Post } from '../../models/post.model';
import { PostCardComponent } from '../../shared/components/post-card/post-card.component';
import { ImageCropperComponent, ImageCropperResult } from '../../shared/components/image-cropper/image-cropper.component';

@Component({
  selector: 'app-profile',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, FormsModule,
    MatButtonModule, MatIconModule, MatTabsModule,
    MatProgressSpinnerModule, MatFormFieldModule, MatInputModule,
    MatSnackBarModule, MatDialogModule, PostCardComponent,
  ],
  templateUrl: './profile.component.html',
  styleUrls: ['./profile.component.scss'],
})
export class ProfileComponent implements OnInit, OnChanges, OnDestroy {
  @Input() username!: string;

  @ViewChild('avatarInput') avatarInput!: ElementRef<HTMLInputElement>;
  @ViewChild('coverInput') coverInput!: ElementRef<HTMLInputElement>;

  profile: User | null = null;
  posts: Post[] = [];
  loading = false;
  currentUser: User | null = null;
  isSelf = false;
  private userSub!: Subscription;

  // Edit profile
  isEditing = false;
  saving = false;
  editForm!: FormGroup;

  // Image uploads
  uploadingAvatar = false;
  uploadingCover = false;

  // Friend request
  friendRequestSent = false;

  // Delete account
  isConfirmingDelete = false;
  deleteInput = '';
  deleting = false;

  constructor(
    private apiService: ApiService,
    private authService: AuthService,
    private fb: FormBuilder,
    private snackBar: MatSnackBar,
    private router: Router,
    private dialog: MatDialog,
  ) {}

  ngOnInit(): void {
    this.userSub = this.authService.currentUser$.subscribe((u) => {
      this.currentUser = u;
      if (this.profile) {
        this.isSelf = this.profile.id === this.currentUser?.id;
      }
    });
    this.loadProfile();
  }

  ngOnChanges(): void {
    this.loadProfile();
  }

  ngOnDestroy(): void {
    this.userSub?.unsubscribe();
  }

  loadProfile(): void {
    if (!this.username) return;
    this.loading = true;
    this.friendRequestSent = false;
    this.apiService.getUser(this.username).subscribe({
      next: (user) => {
        this.profile = user;
        this.isSelf = user.id === this.currentUser?.id;
        this.loading = false;
        this.loadPosts(user.id);
      },
      error: () => (this.loading = false),
    });
  }

  loadPosts(userId: number): void {
    this.apiService.getPosts({ author: userId.toString() }).subscribe({
      next: (res) => (this.posts = res.results),
    });
  }

  openEditDialog(): void {
    if (!this.profile) return;
    this.editForm = this.fb.group({
      first_name: [this.profile.first_name],
      last_name: [this.profile.last_name],
      bio: [this.profile.bio],
      location: [this.profile.location],
      website: [this.profile.website],
    });
    this.isEditing = true;
  }

  saveProfile(): void {
    if (!this.editForm.valid || this.saving) return;
    this.saving = true;
    this.apiService.updateProfile(this.editForm.value).subscribe({
      next: (updated) => {
        this.profile = { ...this.profile!, ...updated };
        this.authService.fetchMe().subscribe();
        this.isEditing = false;
        this.saving = false;
        this.snackBar.open('Profile updated', 'Dismiss', { duration: 3000 });
      },
      error: () => {
        this.saving = false;
        this.snackBar.open('Failed to update profile', 'Dismiss', { duration: 3000 });
      },
    });
  }

  cancelEdit(): void {
    this.isEditing = false;
  }

  openDeleteDialog(): void {
    this.isConfirmingDelete = true;
    this.deleteInput = '';
  }

  cancelDelete(): void {
    this.isConfirmingDelete = false;
  }

  confirmDeleteAccount(): void {
    if (this.deleteInput !== this.currentUser?.username || this.deleting) return;
    this.deleting = true;
    const refresh = this.authService.getRefreshToken() ?? '';
    this.apiService.deleteAccount(refresh).subscribe({
      next: () => this.authService.logout(),
      error: () => {
        this.deleting = false;
        this.snackBar.open('Failed to delete account', 'Dismiss', { duration: 3000 });
      },
    });
  }

  openAvatarPicker(): void { this.avatarInput.nativeElement.click(); }
  openCoverPicker(): void  { this.coverInput.nativeElement.click(); }

  onAvatarSelected(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    const ref = this.dialog.open(ImageCropperComponent, {
      data: { file, aspectRatio: 1, title: 'Crop Avatar' },
      width: '500px',
    });
    ref.afterClosed().subscribe((result: ImageCropperResult | undefined) => {
      if (!result) return;
      const fd = new FormData();
      fd.append('avatar', result.blob, 'avatar.jpg');
      this.uploadingAvatar = true;
      this.apiService.updateProfile(fd).subscribe({
        next: (updated) => {
          this.profile = { ...this.profile!, ...updated };
          this.authService.fetchMe().subscribe();
          this.uploadingAvatar = false;
        },
        error: () => {
          this.uploadingAvatar = false;
          this.snackBar.open('Failed to upload photo', 'Dismiss', { duration: 3000 });
        },
      });
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
      if (!result) return;
      const fd = new FormData();
      fd.append('cover_photo', result.blob, 'cover.jpg');
      this.uploadingCover = true;
      this.apiService.updateProfile(fd).subscribe({
        next: (updated) => {
          this.profile = { ...this.profile!, ...updated };
          this.uploadingCover = false;
        },
        error: () => {
          this.uploadingCover = false;
          this.snackBar.open('Failed to upload banner', 'Dismiss', { duration: 3000 });
        },
      });
    });
  }

  get hasPendingRequest(): boolean {
    return this.friendRequestSent || !!this.profile?.friend_request_sent;
  }

  get hasReceivedRequest(): boolean {
    return !!this.profile?.friend_request_received;
  }

  addFriend(): void {
    if (!this.profile || this.hasPendingRequest) return;
    this.apiService.sendFriendRequest(this.profile.id).subscribe({
      next: () => { this.friendRequestSent = true; },
      error: () => { this.snackBar.open('Could not send friend request', 'Dismiss', { duration: 3000 }); },
    });
  }

  acceptIncomingRequest(): void {
    if (!this.profile) return;
    // Find the request ID by fetching received requests
    this.apiService.getReceivedFriendRequests().subscribe({
      next: (reqs) => {
        const req = reqs.find(r => r.sender.id === this.profile!.id);
        if (req) {
          this.apiService.acceptFriendRequest(req.id).subscribe({
            next: () => {
              if (this.profile) {
                this.profile.is_friend = true;
                this.profile.friend_request_received = false;
              }
              this.snackBar.open('Friend request accepted!', 'Dismiss', { duration: 3000 });
            },
            error: () => this.snackBar.open('Failed to accept request', 'Dismiss', { duration: 3000 }),
          });
        }
      },
    });
  }

  unfriend(): void {
    // For now, just show a message - full unfriend requires backend endpoint
    this.snackBar.open('Unfriend feature coming soon', 'Dismiss', { duration: 3000 });
  }

  startChat(): void {
    if (!this.profile) return;
    this.apiService.createChatRoom({ member_ids: [this.profile.id], room_type: 'direct' }).subscribe({
      next: (room) => this.router.navigate(['/chat', (room as { id: number }).id]),
      error: () => this.snackBar.open('Could not open conversation', 'Dismiss', { duration: 3000 }),
    });
  }

  onPostDeleted(postId: number): void {
    this.posts = this.posts.filter((p) => p.id !== postId);
  }
}
