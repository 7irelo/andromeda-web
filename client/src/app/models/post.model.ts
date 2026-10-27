import { User } from './user.model';

export interface Post {
  id: number;
  author: User;
  content: string;
  post_type: 'text' | 'image' | 'video' | 'link';
  privacy: 'public' | 'friends' | 'private';
  image: string | null;
  video: string | null;
  link_url: string;
  link_title: string;
  link_description: string;
  link_image: string;
  group: number | null;
  page: number | null;
  likes_count: number;
  comments_count: number;
  shares_count: number;
  shared_post: number | null;
  shared_post_data: Post | null;
  is_edited: boolean;
  /** Only meaningful to the author: 'removed' posts are hidden from everyone else. */
  moderation_status?: 'ok' | 'review' | 'removed';
  tags: { name: string }[];
  media: { id: number; file: string; media_type: string; order: number }[];
  my_reaction: string | null;
  created_at: string;
  updated_at: string;
}

export interface Comment {
  id: number;
  post: number;
  author: User;
  content: string;
  parent: number | null;
  likes_count: number;
  replies: Comment[];
  created_at: string;
}

export interface Reaction {
  type: 'like' | 'love' | 'haha' | 'wow' | 'sad' | 'angry';
  emoji: string;
  label: string;
}

export const REACTIONS: Reaction[] = [
  { type: 'like', emoji: '👍', label: 'Like' },
  { type: 'love', emoji: '❤️', label: 'Love' },
  { type: 'haha', emoji: '😂', label: 'Haha' },
  { type: 'wow', emoji: '😮', label: 'Wow' },
  { type: 'sad', emoji: '😢', label: 'Sad' },
  { type: 'angry', emoji: '😡', label: 'Angry' },
];
