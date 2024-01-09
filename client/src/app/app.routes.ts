import { Routes } from '@angular/router';
import { authGuard } from './core/guards/auth.guard';
import { guestGuard } from './core/guards/guest.guard';

export const routes: Routes = [
  {
    path: '',
    redirectTo: 'feed',
    pathMatch: 'full',
  },
  {
    path: 'login',
    canActivate: [guestGuard],
    loadComponent: () =>
      import('./features/auth/login/login.component').then((m) => m.LoginComponent),
  },
  {
    path: 'register',
    canActivate: [guestGuard],
    loadComponent: () =>
      import('./features/auth/register/register.component').then((m) => m.RegisterComponent),
  },
  {
    path: 'feed',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/feed/feed.component').then((m) => m.FeedComponent),
  },
  {
    path: 'profile/:username',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/profile/profile.component').then((m) => m.ProfileComponent),
  },
  {
    path: 'chat',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/chat/chat.component').then((m) => m.ChatComponent),
    children: [
      {
        path: ':roomId',
        loadComponent: () =>
          import('./features/chat/chat-window/chat-window.component').then((m) => m.ChatWindowComponent),
      },
    ],
  },
  {
    path: 'notifications',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/notifications/notifications.component').then((m) => m.NotificationsComponent),
  },
  {
    path: 'friends',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/friends/friends.component').then((m) => m.FriendsComponent),
  },
  {
    path: 'groups',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/groups/groups.component').then((m) => m.GroupsComponent),
  },
  {
    path: 'groups/:id',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/groups/group-detail/group-detail.component').then((m) => m.GroupDetailComponent),
  },
  {
    path: 'marketplace',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/marketplace/marketplace.component').then((m) => m.MarketplaceComponent),
  },
  {
    path: 'marketplace/:id',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/marketplace/listing-detail/listing-detail.component').then((m) => m.ListingDetailComponent),
  },
  {
    path: 'watch',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/watch/watch.component').then((m) => m.WatchComponent),
  },
  {
    path: 'watch/:id',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/watch/video-player/video-player.component').then((m) => m.VideoPlayerComponent),
  },
  {
    path: 'pages',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/pages/pages.component').then((m) => m.PagesComponent),
  },
  {
    path: 'settings',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/settings/settings.component').then((m) => m.SettingsComponent),
  },
  {
    path: '**',
    redirectTo: 'feed',
  },
];
