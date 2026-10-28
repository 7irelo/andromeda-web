import { User } from './user.model';

export type VideoStatus = 'processing' | 'ready' | 'failed';
export type CaptionsStatus = 'none' | 'pending' | 'ready' | 'unavailable';

export interface Video {
  id: number;
  title: string;
  description: string;
  /** Poster frame; a signed link for videos that aren't public. */
  thumbnail_url: string | null;
  sprite_url: string | null;
  /** HLS master playlist (or a plain file for videos uploaded before HLS). */
  playback_url: string | null;
  playback_type: 'hls' | 'file';
  uploader: Pick<User, 'id' | 'username' | 'full_name' | 'avatar_url'>;
  views_count: number;
  likes_count: number;
  comments_count: number;
  duration: number;
  width: number;
  height: number;
  renditions: number[];
  status: VideoStatus;
  /** Only filled in for the uploader. */
  failure_reason: string;
  captions_status: CaptionsStatus;
  is_public: boolean;
  tags: string[];
  is_liked: boolean;
  created_at: string;
  updated_at: string;
}

export interface VideoChapter {
  start_s: number;
  title: string;
}

export interface VideoDetail extends Video {
  chapters: VideoChapter[];
  has_captions: boolean;
  has_transcript: boolean;
  transcript_language: string;
  resume_position_s: number;
  channel: { subscribers_count: number; is_subscribed: boolean };
}

export interface VideoTranscript {
  transcript: string;
  language: string;
}

export interface WatchHistoryEntry {
  video: Video;
  position_s: number;
  updated_at: string;
}

export interface VideoChannel {
  user: Pick<User, 'id' | 'username' | 'full_name' | 'avatar_url' | 'bio'>;
  videos_count: number;
  subscribers_count: number;
  is_subscribed: boolean;
}

export interface ChannelSubscriptionEntry {
  user: Pick<User, 'id' | 'username' | 'full_name' | 'avatar_url'>;
  subscribed_at: string;
}

export interface VideoComment {
  id: number;
  video: number;
  author: Pick<User, 'id' | 'username' | 'full_name' | 'avatar_url'>;
  content: string;
  likes_count: number;
  created_at: string;
}
