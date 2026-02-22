import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatTabsModule } from '@angular/material/tabs';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { User, FriendRequest } from '../../models/user.model';

@Component({
  selector: 'app-friends',
  standalone: true,
  imports: [
    CommonModule, RouterLink, FormsModule, MatIconModule,
    MatButtonModule, MatTabsModule, MatInputModule, MatProgressSpinnerModule,
    MatSnackBarModule,
  ],
  templateUrl: './friends.component.html',
  styleUrls: ['./friends.component.scss'],
})
export class FriendsComponent implements OnInit {
  suggestions: User[] = [];
  receivedRequests: FriendRequest[] = [];
  sentRequests: FriendRequest[] = [];
  searchResults: User[] = [];
  searchQuery = '';
  loading = false;
  currentUserId: number | null = null;

  constructor(
    private apiService: ApiService,
    private authService: AuthService,
    private snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.currentUserId = this.authService.currentUser?.id ?? null;
    this.loadSuggestions();
    this.loadRequests();
  }

  isCurrentUser(user: User): boolean {
    return user.id === this.currentUserId;
  }

  loadSuggestions(): void {
    this.loading = true;
    this.apiService.getSuggestions().subscribe({
      next: (u) => { this.suggestions = u; this.loading = false; },
      error: () => (this.loading = false),
    });
  }

  loadRequests(): void {
    this.apiService.getReceivedFriendRequests().subscribe({
      next: (reqs) => (this.receivedRequests = reqs),
      error: () => {},
    });
    this.apiService.getSentFriendRequests().subscribe({
      next: (reqs) => (this.sentRequests = reqs),
      error: () => {},
    });
  }

  search(): void {
    if (!this.searchQuery.trim()) { this.searchResults = []; return; }
    this.apiService.searchUsers(this.searchQuery).subscribe({
      next: (res) => (this.searchResults = res.results.filter((u) => u.id !== this.currentUserId)),
    });
  }

  accept(req: FriendRequest): void {
    this.apiService.acceptFriendRequest(req.id).subscribe({
      next: () => {
        this.receivedRequests = this.receivedRequests.filter((r) => r.id !== req.id);
        this.snackBar.open('Friend request accepted!', 'Dismiss', { duration: 3000 });
      },
      error: () => this.snackBar.open('Failed to accept request', 'Dismiss', { duration: 3000 }),
    });
  }

  decline(req: FriendRequest): void {
    this.apiService.declineFriendRequest(req.id).subscribe({
      next: () => {
        this.receivedRequests = this.receivedRequests.filter((r) => r.id !== req.id);
      },
      error: () => this.snackBar.open('Failed to decline request', 'Dismiss', { duration: 3000 }),
    });
  }

  cancelRequest(req: FriendRequest): void {
    this.apiService.cancelFriendRequest(req.id).subscribe({
      next: () => {
        this.sentRequests = this.sentRequests.filter((r) => r.id !== req.id);
        this.snackBar.open('Friend request cancelled', 'Dismiss', { duration: 3000 });
      },
      error: () => this.snackBar.open('Failed to cancel request', 'Dismiss', { duration: 3000 }),
    });
  }

  addFriend(user: User): void {
    this.apiService.sendFriendRequest(user.id).subscribe({
      next: () => {
        this.suggestions = this.suggestions.filter((s) => s.id !== user.id);
        this.searchResults = this.searchResults.filter((s) => s.id !== user.id);
        this.snackBar.open('Friend request sent!', 'Dismiss', { duration: 3000 });
      },
      error: () => this.snackBar.open('Could not send friend request', 'Dismiss', { duration: 3000 }),
    });
  }
}
