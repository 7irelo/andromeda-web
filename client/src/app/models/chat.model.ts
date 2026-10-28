import { User } from './user.model';

/** Chat payloads carry only a user's basic public fields. */
export type ChatUser = Pick<User, 'id' | 'username' | 'first_name' | 'last_name' | 'full_name' | 'avatar_url' | 'is_verified'>;

export type ReactionKey = 'like' | 'love' | 'haha' | 'wow' | 'sad' | 'angry';

export const REACTIONS: { key: ReactionKey; emoji: string; label: string }[] = [
  { key: 'like', emoji: '\u{1F44D}', label: 'Like' },
  { key: 'love', emoji: '❤️', label: 'Love' },
  { key: 'haha', emoji: '\u{1F602}', label: 'Haha' },
  { key: 'wow', emoji: '\u{1F62E}', label: 'Wow' },
  { key: 'sad', emoji: '\u{1F622}', label: 'Sad' },
  { key: 'angry', emoji: '\u{1F620}', label: 'Angry' },
];

export interface ReactionCount {
  reaction: ReactionKey;
  count: number;
}

export interface Message {
  id: number;
  room: number;
  sender: ChatUser | null;
  content: string;
  message_type: 'text' | 'image' | 'video' | 'file' | 'voice';
  file_url: string | null;
  reply_to: number | null;
  reply_to_data: {
    id: number;
    content: string;
    message_type: Message['message_type'];
    is_deleted: boolean;
    sender: string | null;
  } | null;
  is_edited: boolean;
  edited_at: string | null;
  is_deleted: boolean;
  read_by_count: number;
  duration_s: number | null;
  transcript: string;
  transcript_status: '' | 'pending' | 'done' | 'failed';
  reactions: ReactionCount[];
  my_reaction: ReactionKey | null;
  created_at: string;
  updated_at: string;
}

export interface ChatMember {
  id: number;
  user: ChatUser;
  role: 'member' | 'admin';
  last_read_at: string | null;
  joined_at: string;
}

export interface ChatRoom {
  id: number;
  room_type: 'direct' | 'group';
  name: string;
  avatar: string | null;
  members: ChatMember[];
  my_role: 'member' | 'admin' | null;
  last_message: Pick<Message, 'id' | 'sender' | 'content' | 'message_type' | 'created_at'> | null;
  unread_count: number;
  created_at: string;
  updated_at: string;
}

export interface ChatUnread {
  total: number;
  rooms_with_unread: number;
  rooms: Record<number, number>;
}

export interface MessagesAfter {
  results: Message[];
  has_more: boolean;
}

export interface ReactionEvent {
  message_id: number;
  user_id: number;
  reaction: ReactionKey | null;
  reactions: ReactionCount[];
}

export interface StatusEvent {
  user_id: number;
  username: string;
  status: 'online' | 'offline';
}

export interface TypingEvent {
  user_id: number;
  username: string;
  is_typing: boolean;
}

export interface WsMessage {
  type: 'message' | 'message_updated' | 'reaction' | 'typing' | 'read' | 'status' | 'presence'
    | 'room_updated' | 'member_removed' | 'error';
  [key: string]: unknown;
}

export interface CitedPoint {
  text: string;
  message_ids: number[];
}

export interface CatchUp {
  tldr: string;
  topics: { title: string; summary: string; message_ids: number[] }[];
  decisions: CitedPoint[];
  questions_for_you: CitedPoint[];
  message_count: number;
}
