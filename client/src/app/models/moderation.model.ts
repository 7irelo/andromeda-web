export type ReportableType = 'post' | 'comment' | 'listing' | 'message' | 'user' | 'video';

export interface ReportReason {
  key: string;
  label: string;
}

export type ModerationActionKind = 'approve' | 'remove' | 'restore' | 'warn' | 'suspend' | 'ban' | 'dismiss';

export interface ModerationCase {
  id: number;
  content_type: ReportableType;
  object_id: number;
  author_id: number | null;
  author_username: string | null;
  content: string;
  snapshot: string;
  decision: 'allow' | 'review' | 'remove';
  categories: string[];
  confidence: number;
  reason: string;
  model: string;
  stages: string[];
  degraded: boolean;
  source: 'auto' | 'report';
  report_count: number;
  reports: { id: number; reason: string; details: string; created_at: string }[];
  actions: { id: number; action: string; note: string; moderator_username: string | null; automated_by: string;
    created_at: string }[];
  appeal: Appeal | null;
  resolved: boolean;
  created_at: string;
}

export interface Appeal {
  id: number;
  message: string;
  status: 'open' | 'upheld' | 'restored';
  created_at: string;
  decided_at: string | null;
}

export interface MyCase {
  id: number;
  content_type: ReportableType;
  object_id: number;
  snapshot: string;
  categories: string[];
  created_at: string;
  appeal: Appeal | null;
}

export interface DataExportEntry {
  id: number;
  status: 'pending' | 'ready' | 'failed';
  size_bytes: number;
  created_at: string;
  expires_at: string | null;
}
