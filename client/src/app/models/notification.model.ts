import { User } from './user.model';

export interface Notification {
  id: number;
  sender: User | null;
  notification_type: string;
  title: string;
  body: string;
  is_read: boolean;
  extra: Record<string, unknown>;
  created_at: string;
}
