import { Component, OnInit } from '@angular/core';
import { RouterLink, RouterLinkActive, Router } from '@angular/router';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatBadgeModule } from '@angular/material/badge';
import { MatMenuModule } from '@angular/material/menu';
import { MatButtonModule } from '@angular/material/button';
import { MatInputModule } from '@angular/material/input';
import { FormsModule } from '@angular/forms';
import { AuthService } from '../../../core/services/auth.service';
import { WebSocketService } from '../../../core/services/websocket.service';
import { ApiService } from '../../../core/services/api.service';
import { User } from '../../../models/user.model';

@Component({
  selector: 'app-navbar',
  standalone: true,
  imports: [
    CommonModule, RouterLink, RouterLinkActive,
    MatIconModule, MatBadgeModule, MatMenuModule,
    MatButtonModule, MatInputModule, FormsModule,
  ],
  templateUrl: './navbar.component.html',
  styleUrls: ['./navbar.component.scss'],
})
export class NavbarComponent implements OnInit {
  currentUser: User | null = null;
  unreadNotifications = 0;
  searchQuery = '';

  navItems = [
    { icon: 'home', label: 'Feed', route: '/feed' },
    { icon: 'people', label: 'Friends', route: '/friends' },
    { icon: 'group', label: 'Groups', route: '/groups' },
    { icon: 'play_circle', label: 'Watch', route: '/watch' },
    { icon: 'storefront', label: 'Marketplace', route: '/marketplace' },
  ];

  constructor(
    public authService: AuthService,
    private wsService: WebSocketService,
    private apiService: ApiService,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.authService.currentUser$.subscribe((u) => (this.currentUser = u));
    this.wsService.unreadCount$.subscribe((n) => (this.unreadNotifications = n));
    this.apiService.getUnreadCount().subscribe(({ unread_count }) => {
      this.wsService.unreadCount$.next(unread_count);
    });
  }

  search(): void {
    if (this.searchQuery.trim()) {
      this.router.navigate(['/friends'], { queryParams: { q: this.searchQuery } });
    }
  }

  logout(): void {
    this.authService.logout();
  }
}
