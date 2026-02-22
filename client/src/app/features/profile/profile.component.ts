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
import { Subscription } from 'rxjs';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { User } from '../../models/user.model';
import { Post } from '../../models/post.model';
import { PostCardComponent } from '../../shared/components/post-card/post-card.component';

@Component({
  selector: 'app-profile',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, FormsModule,
    MatButtonModule, MatIconModule, MatTabsModule,
    MatProgressSpinnerModule, MatFormFieldModule, MatInputModule,
    MatSnackBarModule, PostCardComponent,
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
    const fd = new FormData();
    fd.append('avatar', file);
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
  }

  onCoverSelected(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('cover_photo', file);
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
  }

  follow(): void {
    if (!this.profile) return;
    if (this.profile.is_following) {
      this.apiService.unfollowUser(this.profile.id).subscribe(() => {
        if (this.profile) { this.profile.is_following = false; this.profile.followers_count--; }
      });
    } else {
      this.apiService.followUser(this.profile.id).subscribe(() => {
        if (this.profile) { this.profile.is_following = true; this.profile.followers_count++; }
      });
    }
  }

  get hasPendingRequest(): boolean {
    return this.friendRequestSent || !!this.profile?.friend_request_sent;
  }

  addFriend(): void {
    if (!this.profile || this.hasPendingRequest) return;
    this.apiService.sendFriendRequest(this.profile.id).subscribe({
      next: () => { this.friendRequestSent = true; },
      error: () => { this.snackBar.open('Could not send friend request', 'Dismiss', { duration: 3000 }); },
    });
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
