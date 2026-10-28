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
  /** Present when the post was published into a group. */
  group_data?: { id: number; name: string } | null;
  /** Present when the post was published as a page. */
  page_data?: { id: number; name: string; username: string; avatar_url: string | null } | null;
  likes_count: number;
  comments_count: number;
  shares_count: number;
  shared_post: number | null;
  /** `{ id: null, unavailable: true }` when the original is no longer visible to you. */
  shared_post_data: (Post & { unavailable?: boolean }) | null;
  is_edited: boolean;
  /** Only meaningful to the author: 'removed' posts are hidden from everyone else. */
  moderation_status?: 'ok' | 'review' | 'removed';
  tags: { name: string }[];
  media: PostMedia[];
  my_reaction: string | null;
  is_saved?: boolean;
  /** Feed only: a short "Why am I seeing this?" explanation. */
  reason?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PostMedia {
  id: number;
  file: string;
  media_type: string;
  order: number;
}

export interface PostRevision {
  id: number;
  content: string;
  created_at: string;
}

export type FeedSort = 'top' | 'latest';

/** The home feed is cursor-paginated: follow `next_cursor` until it is null. */
export interface FeedPage {
  next: string | null;
  next_cursor: string | null;
  previous: string | null;
  results: Post[];
}

export interface Comment {
  id: number;
  post: number;
  author: User;
  content: string;
  parent: number | null;
  likes_count: number;
  liked?: boolean;
  is_edited?: boolean;
  /** True when you may delete it: your comment, a comment on your post, or you moderate the group/page. */
  can_delete?: boolean;
  replies: Comment[];
  created_at: string;
  updated_at?: string;
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
