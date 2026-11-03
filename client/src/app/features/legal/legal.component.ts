import { Component, ChangeDetectionStrategy, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';

/**
 * Privacy policy and terms of use. Plain-language summaries of how the app
 * actually behaves; the version matches POLICY_VERSION on the server, which
 * is recorded with every consent.
 */
@Component({
    selector: 'app-legal',
    imports: [CommonModule, RouterLink],
    template: `
    <article class="legal card" *ngIf="page === 'privacy'">
      <h1>Privacy policy</h1>
      <p class="version">Version 2026-10-28</p>

      <h2>What we keep</h2>
      <ul>
        <li>Your account details: name, username, email address and the profile details you add.</li>
        <li>What you share: posts, comments, messages, listings, videos, voice notes and the photos in them.</li>
        <li>Your connections: friends, groups, pages you follow and people you block.</li>
        <li>Security records: the devices you're signed in on (browser name and a coarse network range, never your
          full IP address) and the consents you've given.</li>
      </ul>

      <h2>Who sees it</h2>
      <p>Your privacy settings decide who sees your profile, posts and friends list. Blocking someone hides you from each
        other everywhere. Messages are visible only to the people in the conversation. Moderators can see content that
        was reported or flagged, and only to decide what to do about it.</p>

      <h2>AI features</h2>
      <p>Search, Ask Andromeda, chat summaries, voice-note transcripts and the listing assistant send the relevant text,
        audio or photos to our AI service, which uses Anthropic, OpenAI and Deepgram. These providers process the data to
        give you the result and aren't allowed to train on it. AI features only ever see content you could see yourself.
        You can turn them off in <a routerLink="/settings">Settings</a>: your content is then removed from the search index
        and isn't used to answer anyone's questions. Safety checks on new content still run.</p>

      <h2>Cookies</h2>
      <p>We use one cookie, to keep you signed in. It can't be read by scripts and is sent only to our sign-in endpoints.
        There are no advertising or analytics cookies.</p>

      <h2>Your rights</h2>
      <ul>
        <li><strong>Access:</strong> download everything we hold about you from Settings. The file is ready within minutes
          and available for 7 days.</li>
        <li><strong>Correction:</strong> edit your profile and content at any time.</li>
        <li><strong>Deletion:</strong> delete your account from Settings. It's locked straight away and permanently erased
          after 14 days, including your photos, videos, messages and search data. Signing in before then cancels it.</li>
        <li><strong>Objection:</strong> turn off AI features, email digests and push notifications in Settings.</li>
      </ul>
      <p>We handle personal information in line with POPIA and the GDPR.</p>
    </article>

    <article class="legal card" *ngIf="page === 'terms'">
      <h1>Terms of use</h1>
      <p class="version">Version 2026-10-28</p>

      <h2>Your account</h2>
      <p>Keep your password private and turn on two-factor sign-in if you can. You're responsible for what's shared from
        your account. One person, one account; don't impersonate anyone.</p>

      <h2>Community guidelines</h2>
      <p>Don't share content that harasses or threatens people, attacks them for who they are, is sexually explicit, promotes
        self-harm, shares someone's private information, or is spam. In the marketplace, don't sell illegal or dangerous goods,
        and don't run scams such as asking for deposits before an item is seen.</p>

      <h2>Moderation</h2>
      <p>New content is checked automatically, and anyone can report something they think breaks these rules. Clear breaks
        are removed and you'll be told why. Borderline cases go to a person. You can appeal a removal once and a moderator
        will look at it again. Repeated or serious breaks can lead to a warning, a suspension or a ban.</p>

      <h2>Your content</h2>
      <p>You own what you post. You give Andromeda permission to store and show it to the people your settings allow, for as
        long as it stays on the service.</p>

      <h2>AI features</h2>
      <p>AI answers, summaries and suggestions can be wrong. Check the sources they link to before relying on them.</p>
    </article>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    .legal { max-width: 720px; margin: var(--space-6) auto; padding: var(--space-8); font-size: var(--font-size-base);
      line-height: 1.6; color: var(--text-secondary); }
    .legal h1 { margin: 0 0 var(--space-1); font-size: var(--font-size-xl); font-weight: 600; line-height: 1.3;
      letter-spacing: -.01em; color: var(--text-primary); }
    .legal h2 { margin: var(--space-6) 0 var(--space-2); font-size: var(--font-size-base); font-weight: 600; line-height: 1.4;
      letter-spacing: 0; color: var(--text-primary); }
    .legal p { margin: 0 0 var(--space-3); }
    .legal ul { margin: 0 0 var(--space-3); padding-left: var(--space-5); }
    .legal li { margin-bottom: var(--space-1); }
    .legal strong { font-weight: 600; color: var(--text-primary); }
    .legal a { text-decoration: underline; }
    .legal .version { font-size: var(--font-size-sm); color: var(--text-muted); }
    @media (max-width: 760px) {
      .legal { margin: var(--space-4); padding: var(--space-5) var(--space-4); }
    }
  `]
})
export class LegalComponent {
  readonly page: 'privacy' | 'terms' = inject(ActivatedRoute).snapshot.data['page'];
}
