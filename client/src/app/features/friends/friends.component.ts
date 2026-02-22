import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatTabsModule } from '@angular/material/tabs';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { User, FriendRequest } from '../../models/user.model';

@Component({
  selector: 'app-friends',
  standalone: true,
  imports: [
    CommonModule, RouterLink, FormsModule, MatIconModule,
    MatButtonModule, MatTabsModule, MatInputModule, MatProgressSpinnerModule,
  ],
  templateUrl: './friends.component.html',
  styleUrls: ['./friends.component.scss'],
})
export class FriendsComponent implements OnInit {
  suggestions: User[] = [];
  friendRequests: FriendRequest[] = [];
  searchResults: User[] = [];
  searchQuery = '';
  loading = false;
  currentUserId: number | null = null;

  constructor(private apiService: ApiService, private authService: AuthService) {}

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
    this.apiService.getFriendRequests().subscribe({
      next: (res) => {
        this.friendRequests = res.results.filter((r) => r.status === 'pending');
      },
    });
  }

  search(): void {
    if (!this.searchQuery.trim()) { this.searchResults = []; return; }
    this.apiService.searchUsers(this.searchQuery).subscribe({
      next: (res) => (this.searchResults = res.results.filter((u) => u.id !== this.currentUserId)),
    });
  }

  accept(req: FriendRequest): void {
    this.apiService.acceptFriendRequest(req.id).subscribe(() => {
      this.friendRequests = this.friendRequests.filter((r) => r.id !== req.id);
    });
  }

  decline(req: FriendRequest): void {
    this.apiService.declineFriendRequest(req.id).subscribe(() => {
      this.friendRequests = this.friendRequests.filter((r) => r.id !== req.id);
    });
  }

  addFriend(user: User): void {
    this.apiService.sendFriendRequest(user.id).subscribe({
      next: () => {
        this.suggestions = this.suggestions.filter((s) => s.id !== user.id);
        this.searchResults = this.searchResults.filter((s) => s.id !== user.id);
      },
    });
  }
}
