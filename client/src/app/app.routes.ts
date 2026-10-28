import { Routes } from '@angular/router';
import { staffGuard } from './core/guards/staff.guard';
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
    path: 'forgot-password',
    canActivate: [guestGuard],
    loadComponent: () =>
      import('./features/auth/password-reset/forgot-password.component').then((m) => m.ForgotPasswordComponent),
  },
  {
    path: 'moderation',
    canActivate: [authGuard, staffGuard],
    loadComponent: () =>
      import('./features/moderation/moderation-console.component').then((m) => m.ModerationConsoleComponent),
  },
  {
    path: 'decisions',
    canActivate: [authGuard],
    loadComponent: () => import('./features/moderation/my-decisions.component').then((m) => m.MyDecisionsComponent),
  },
  {
    path: 'privacy',
    data: { page: 'privacy' },
    loadComponent: () => import('./features/legal/legal.component').then((m) => m.LegalComponent),
  },
  {
    path: 'terms',
    data: { page: 'terms' },
    loadComponent: () => import('./features/legal/legal.component').then((m) => m.LegalComponent),
  },
  {
    // Reachable signed in or out: the link arrives by email.
    path: 'verify-email',
    loadComponent: () =>
      import('./features/auth/verify-email/verify-email.component').then((m) => m.VerifyEmailComponent),
  },
  {
    // Reachable signed in or out: the link arrives by email.
    path: 'reset-password',
    loadComponent: () =>
      import('./features/auth/password-reset/reset-password.component').then((m) => m.ResetPasswordComponent),
  },
  {
    path: 'feed',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/feed/feed.component').then((m) => m.FeedComponent),
  },
  {
    path: 'posts/:id',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/posts/post-detail.component').then((m) => m.PostDetailComponent),
  },
  {
    path: 'tags/:name',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/tags/tag-posts.component').then((m) => m.TagPostsComponent),
  },
  {
    path: 'saved',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/saved/saved-posts.component').then((m) => m.SavedPostsComponent),
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
    path: 'groups/join/:token',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/groups/group-join/group-join.component').then((m) => m.GroupJoinComponent),
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
    path: 'marketplace/mine',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/marketplace/my-listings/my-listings.component').then((m) => m.MyListingsComponent),
  },
  {
    path: 'marketplace/saved',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/marketplace/saved-listings/saved-listings.component').then((m) => m.SavedListingsComponent),
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
    path: 'watch/history',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/watch/watch-history/watch-history.component').then((m) => m.WatchHistoryComponent),
  },
  {
    path: 'watch/channel/:userId',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/watch/channel/channel.component').then((m) => m.ChannelComponent),
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
    path: 'pages/:id',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/pages/page-detail/page-detail.component').then((m) => m.PageDetailComponent),
  },
  {
    path: 'search',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/search/search.component').then((m) => m.SearchComponent),
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
