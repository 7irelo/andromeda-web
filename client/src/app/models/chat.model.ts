import { User } from './user.model';

export interface Message {
  id: number;
  room: number;
  sender: User;
  content: string;
  message_type: 'text' | 'image' | 'video' | 'file';
  file: string | null;
  reply_to: number | null;
  reply_to_data: { id: number; content: string; sender: string } | null;
  is_edited: boolean;
  is_deleted: boolean;
  read_by_count: number;
  created_at: string;
  updated_at: string;
}

export interface ChatMember {
  id: number;
  user: User;
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
  last_message: Message | null;
  unread_count: number;
  created_at: string;
  updated_at: string;
}

export interface WsMessage {
  type: 'message' | 'typing' | 'read' | 'status' | 'notification';
  [key: string]: unknown;
}
