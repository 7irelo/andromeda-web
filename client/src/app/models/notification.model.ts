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
  updated_at?: string;
  type?: string;
}

export interface NotificationCategory {
  key: string;
  label: string;
  locked: boolean;
  in_app: boolean;
  push: boolean;
  email: boolean;
}

export interface NotificationPreferences {
  categories: NotificationCategory[];
  email_digest: 'off' | 'daily';
  listing_digest: boolean;
  push_available: boolean;
}
