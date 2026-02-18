import { Component, Input, OnInit, OnChanges, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup } from '@angular/forms';
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
    CommonModule, ReactiveFormsModule,
    MatButtonModule, MatIconModule, MatTabsModule,
    MatProgressSpinnerModule, MatFormFieldModule, MatInputModule,
    MatSnackBarModule, PostCardComponent,
  ],
  templateUrl: './profile.component.html',
  styleUrls: ['./profile.component.scss'],
})
export class ProfileComponent implements OnInit, OnChanges, OnDestroy {
  @Input() username!: string;

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

  constructor(
    private apiService: ApiService,
    private authService: AuthService,
    private fb: FormBuilder,
    private snackBar: MatSnackBar,
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

  addFriend(): void {
    if (!this.profile) return;
    this.apiService.sendFriendRequest(this.profile.id).subscribe();
  }

  onPostDeleted(postId: number): void {
    this.posts = this.posts.filter((p) => p.id !== postId);
  }
}
