import { User } from './user.model';

export interface Video {
  id: number;
  title: string;
  description: string;
  video_file: string;
  thumbnail: string | null;
  uploader: Pick<User, 'id' | 'username' | 'full_name' | 'avatar_url'>;
  views_count: number;
  likes_count: number;
  comments_count: number;
  duration: number;
  is_liked: boolean;
  created_at: string;
  updated_at: string;
}

export interface VideoComment {
  id: number;
  video: number;
  author: Pick<User, 'id' | 'username' | 'full_name' | 'avatar_url'>;
  content: string;
  likes_count: number;
  created_at: string;
}
