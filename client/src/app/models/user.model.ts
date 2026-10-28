export interface User {
  id: number;
  username: string;
  /** Only present on the signed-in user's own record. */
  email?: string;
  first_name: string;
  last_name: string;
  full_name: string;
  bio: string;
  avatar_url: string | null;
  cover_photo_url: string | null;
  location: string;
  website: string;
  birth_date?: string | null;
  is_verified: boolean;
  friends_count: number;
  posts_count: number;
  created_at: string;
  is_friend?: boolean;
  friend_request_sent?: boolean;
  friend_request_received?: boolean;
  is_blocked?: boolean;

  // Privacy settings
  privacy_profile?: string;
  privacy_messages?: string;
  privacy_friend_requests?: string;
  privacy_friends_list?: string;
  default_post_privacy?: string;
  show_online_status?: boolean;
  searchable?: boolean;
  email_verified?: boolean;
  ai_opt_out?: boolean;
}

export interface FriendRequest {
  id: number;
  sender: User;
  receiver: User;
  status: 'pending' | 'accepted' | 'declined';
  created_at: string;
}

/** Returned by login, register and password change. The refresh token arrives as an HttpOnly cookie. */
export interface SessionResponse {
  access: string;
  user: User;
}

/** Returned instead of a session when the account has two-factor sign-in on. */
export interface MfaChallenge {
  mfa_required: true;
  mfa_token: string;
}

export interface DeviceSession {
  id: string;
  user_agent: string;
  network: string;
  created_at: string;
  last_seen_at: string;
  current: boolean;
}

export interface MfaStatus {
  enabled: boolean;
  recovery_codes_left: number;
}

export interface MfaSetup {
  secret: string;
  otpauth_uri: string;
  qr_png: string;
}
