/** Smart replies and compose assist (AI writing help). */

export interface ReplySuggestion {
  /** Keyed hash of the text: the only thing the server stores. */
  id: string;
  text: string;
}

export interface ReplySuggestions {
  suggestions: ReplySuggestion[];
  variant: string | null;
  anchor_id: number | null;
}

export type ReplyFeedbackAction = 'accepted' | 'edited' | 'dismissed';

export type ComposeAction = 'friendlier' | 'formal' | 'shorter' | 'grammar' | 'translate';
export type ComposeLanguage = 'en' | 'zu' | 'af' | 'st' | 'xh';

export interface ComposeAssistRequest {
  text: string;
  action: ComposeAction;
  language?: ComposeLanguage;
  kind: 'post' | 'listing';
}

export interface ComposeAssistResult {
  text: string;
  truncated: boolean;
}

export const COMPOSE_MAX_CHARS = 5000;

export const COMPOSE_TONES: { action: Exclude<ComposeAction, 'translate'>; label: string; icon: string }[] = [
  { action: 'friendlier', label: 'Friendlier', icon: 'sentiment_satisfied' },
  { action: 'formal', label: 'More formal', icon: 'business_center' },
  { action: 'shorter', label: 'Shorter', icon: 'short_text' },
  { action: 'grammar', label: 'Fix grammar', icon: 'spellcheck' },
];

export const COMPOSE_LANGUAGES: { code: ComposeLanguage; label: string }[] = [
  { code: 'en', label: 'English' },
  { code: 'zu', label: 'isiZulu' },
  { code: 'af', label: 'Afrikaans' },
  { code: 'st', label: 'Sesotho' },
  { code: 'xh', label: 'isiXhosa' },
];
