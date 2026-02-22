import { User } from './user.model';

export interface Group {
  id: number;
  name: string;
  description: string;
  cover_photo: string | null;
  privacy: 'public' | 'private' | 'secret';
  creator: Pick<User, 'id' | 'username' | 'full_name' | 'avatar_url'>;
  members_count: number;
  is_member: boolean;
  created_at: string;
  updated_at: string;
}

export interface GroupMember {
  id: number;
  user: Pick<User, 'id' | 'username' | 'full_name' | 'avatar_url'>;
  role: 'admin' | 'moderator' | 'member';
  joined_at: string;
}
