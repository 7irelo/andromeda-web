import { User } from './user.model';

export interface Page {
  id: number;
  name: string;
  description: string;
  avatar: string | null;
  cover_photo: string | null;
  category: string;
  owner: Pick<User, 'id' | 'username' | 'full_name' | 'avatar_url'>;
  followers_count: number;
  is_following: boolean;
  created_at: string;
  updated_at: string;
}
