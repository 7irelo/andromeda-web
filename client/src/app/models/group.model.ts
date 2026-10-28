import { User } from './user.model';

export type GroupPrivacy = 'public' | 'private' | 'secret';
export type GroupRole = 'admin' | 'moderator' | 'member';

export interface Group {
  id: number;
  name: string;
  description: string;
  cover_photo: string | null;
  avatar?: string | null;
  privacy: GroupPrivacy;
  created_by?: Pick<User, 'id' | 'username' | 'full_name' | 'avatar_url'> | null;
  members_count: number;
  is_member: boolean;
  my_role?: GroupRole | null;
  /** True when the signed-in user is banned from this group. */
  is_banned?: boolean;
  /** True when the signed-in user has a pending join request. */
  has_requested?: boolean;
  created_at: string;
}

export interface GroupMember {
  id: number;
  user: Pick<User, 'id' | 'username' | 'full_name' | 'avatar_url'>;
  role: GroupRole;
  joined_at: string;
}

export interface GroupJoinRequest {
  id: number;
  user: User;
  status: string;
  created_at: string;
}

export interface GroupRule {
  id?: number;
  position?: number;
  title: string;
  description: string;
}

export interface GroupBan {
  id: number;
  user: Pick<User, 'id' | 'username' | 'full_name' | 'avatar_url'>;
  reason: string;
  created_at: string;
}

export interface GroupInvite {
  id: number;
  created_by: Pick<User, 'id' | 'username' | 'full_name'> | null;
  expires_at: string;
  max_uses: number | null;
  uses_count: number;
  revoked_at: string | null;
  is_usable: boolean;
  created_at: string;
  /** Only present in the response that created the invite. */
  token?: string;
}

export interface GroupInvitePreview {
  group: Pick<Group, 'id' | 'name' | 'description' | 'cover_photo' | 'avatar' | 'privacy' | 'members_count'> & {
    rules: GroupRule[];
  };
  is_member: boolean;
  expires_at: string;
}
