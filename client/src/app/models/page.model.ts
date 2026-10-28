import { User } from './user.model';

export type PageRole = 'admin' | 'editor' | 'analyst';

export interface Page {
  id: number;
  name: string;
  username: string;
  description: string;
  avatar: string | null;
  cover_photo: string | null;
  category: string;
  website: string;
  email: string;
  phone: string;
  /** Granted by staff only. */
  is_verified: boolean;
  created_by: Pick<User, 'id' | 'username' | 'full_name' | 'avatar_url'> | null;
  followers_count: number;
  is_following: boolean;
  /** The signed-in user's role on this page, if any. */
  my_role: PageRole | null;
  created_at: string;
}

export interface PageTeamMember {
  id: number;
  user: Pick<User, 'id' | 'username' | 'full_name' | 'avatar_url'>;
  role: PageRole;
}

export const PAGE_CATEGORIES = [
  { value: 'business', label: 'Business' },
  { value: 'community', label: 'Community' },
  { value: 'entertainment', label: 'Entertainment' },
  { value: 'education', label: 'Education' },
  { value: 'government', label: 'Government' },
  { value: 'nonprofit', label: 'Non-profit' },
  { value: 'other', label: 'Other' },
];
