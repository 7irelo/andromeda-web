import { ChangeDetectionStrategy, Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';

interface Segment {
  kind: 'text' | 'tag' | 'mention';
  text: string;
  value?: string;
}

// Mirrors HASHTAG_RE / MENTION_RE in server/posts/tasks.py (Python's \w is Unicode-aware).
const TOKEN_RE = /(?<![\p{L}\p{N}_#])#([\p{L}\p{N}_]{2,50})|(?<![\p{L}\p{N}_@])@([\p{L}\p{N}_.@+-]{2,150})/gu;

/** Splits text into plain runs and links for #hashtags and @mentions. Never uses innerHTML. */
export function segmentText(text: string): Segment[] {
  const out: Segment[] = [];
  let last = 0;
  for (const m of (text || '').matchAll(TOKEN_RE)) {
    const start = m.index ?? 0;
    let raw = m[0];
    let value = m[1] ?? m[2];
    if (m[2]) {
      // "@thandi." at the end of a sentence: the full stop isn't part of the name.
      const trimmed = value.replace(/[.]+$/, '');
      raw = raw.slice(0, raw.length - (value.length - trimmed.length));
      value = trimmed;
    }
    if (start > last) out.push({ kind: 'text', text: text.slice(last, start) });
    out.push({ kind: m[1] ? 'tag' : 'mention', text: raw, value: m[1] ? value.toLowerCase() : value });
    last = start + raw.length;
  }
  if (last < (text || '').length) out.push({ kind: 'text', text: text.slice(last) });
  return out;
}

@Component({
  selector: 'app-post-text',
  imports: [CommonModule, RouterLink],
  changeDetection: ChangeDetectionStrategy.Eager,
  template: `<ng-container *ngFor="let s of segments"><ng-container [ngSwitch]="s.kind"><a
    *ngSwitchCase="'tag'" class="token" [routerLink]="['/tags', s.value]">{{ s.text }}</a><a
    *ngSwitchCase="'mention'" class="token" [routerLink]="['/profile', s.value]">{{ s.text }}</a><ng-container
    *ngSwitchDefault>{{ s.text }}</ng-container></ng-container></ng-container>`,
  styles: [`
    :host { white-space: pre-wrap; overflow-wrap: anywhere; }
    .token { color: var(--primary); font-weight: 500; text-decoration: none; }
    .token:hover, .token:focus-visible { text-decoration: underline; }
  `],
})
export class PostTextComponent {
  segments: Segment[] = [];

  @Input() set text(value: string | null | undefined) {
    this.segments = segmentText(value ?? '');
  }
}
