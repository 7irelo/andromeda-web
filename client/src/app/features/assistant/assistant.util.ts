import { AssistantRun, AssistantStep } from '../../models/assistant.model';

/** Only links into the app itself, in the shapes the server produces. */
const CITATION_URL = /^\/(posts|marketplace|groups|pages|watch)\/\d+$/;

export function safeCitationUrl(url: string | null | undefined): string | null {
  return url && CITATION_URL.test(url) ? url : null;
}

const TOOL_LABELS: Record<string, string> = {
  search_content: 'Searching posts and listings',
  get_post: 'Reading a post',
  list_my_groups: 'Checking your groups',
  list_my_chats: 'Checking your chats',
  find_people: 'Looking people up',
  search_listings: 'Searching the marketplace',
  summarise_thread: 'Summarising a chat',
  draft_post: 'Drafting a post',
  draft_message: 'Drafting a message',
  create_post: 'Preparing a post for your approval',
  send_message: 'Preparing a message for your approval',
};

export function stepLabel(step: AssistantStep): string {
  if (step.kind === 'route') return 'Understanding your request';
  if (step.kind === 'model') return 'Thinking';
  return TOOL_LABELS[step.tool_name] ?? 'Using a tool';
}

export function isActive(run: AssistantRun): boolean {
  return run.status === 'queued' || run.status === 'running';
}
