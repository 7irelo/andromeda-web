export type AssistantRunStatus = 'queued' | 'running' | 'awaiting_approval' | 'done' | 'failed';
export type AssistantPath = '' | 'search' | 'draft_post' | 'draft_message' | 'summarise' | 'agent';
export type ProposalStatus = 'pending' | 'approved' | 'rejected' | 'expired' | 'failed';

export interface AssistantCitation {
  id: string;
  type: 'posts' | 'listings' | 'groups' | 'pages' | 'videos';
  title: string;
  url: string;
}

export interface AssistantStep {
  index: number;
  kind: 'route' | 'model' | 'tool';
  tool_name: string;
  is_error: boolean;
  created_at: string;
}

export interface ProposalPreview {
  action: 'post' | 'message';
  text: string;
  links: string[];
  audience?: string;
  group?: { id: number; name: string } | null;
  to?: { id: number; username: string; name: string }[];
  room?: { id: number; name: string | null } | null;
}

export interface AssistantProposal {
  id: number;
  run: number | null;
  source: 'assistant' | 'mcp';
  tool: 'create_post' | 'send_message';
  preview: ProposalPreview;
  status: ProposalStatus;
  result: { url?: string; post_id?: number; room_id?: number };
  error: string;
  created_at: string;
  expires_at: string;
  decided_at: string | null;
}

export interface AssistantRun {
  id: number;
  request_text: string;
  follow_up_of: number | null;
  path: AssistantPath;
  status: AssistantRunStatus;
  step_count: number;
  total_tokens: number;
  cost_usd: string;
  answer: string;
  citations: AssistantCitation[];
  error: string;
  steps: AssistantStep[];
  proposals: AssistantProposal[];
  created_at: string;
  updated_at: string;
}

/** Pushed on the notification socket; the panel refetches the run it names. */
export interface AssistantEvent {
  type: 'assistant.event';
  event: 'assistant.step' | 'assistant.proposal' | 'assistant.awaiting_approval' | 'assistant.done' | 'assistant.failed';
  run_id: number;
  status?: AssistantRunStatus;
  proposal_id?: number;
  step?: { index: number; kind: string; tool?: string; is_error: boolean };
}

export type TokenScope = 'read' | 'propose';

export interface AccessToken {
  id: number;
  name: string;
  prefix: string;
  scopes: TokenScope[];
  created_at: string;
  expires_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

/** Returned once, at creation. */
export interface NewAccessToken extends AccessToken {
  token: string;
}
