export interface User {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  bio: string;
  avatar_url: string | null;
  cover_photo_url: string | null;
  location: string;
  website: string;
  birth_date: string | null;
  is_verified: boolean;
  friends_count: number;
  posts_count: number;
  created_at: string;
  is_friend?: boolean;
  friend_request_sent?: boolean;
  friend_request_received?: boolean;

  // Privacy settings
  privacy_profile?: string;
  privacy_messages?: string;
  privacy_friend_requests?: string;
  privacy_friends_list?: string;
  default_post_privacy?: string;
  show_online_status?: boolean;
  searchable?: boolean;
}

export interface FriendRequest {
  id: number;
  sender: User;
  receiver: User;
  status: 'pending' | 'accepted' | 'declined';
  created_at: string;
}

export interface AuthTokens {
  access: string;
  refresh: string;
}

export interface LoginResponse {
  user: User;
  tokens: AuthTokens;
}
