import { Component, Type } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideServiceWorker } from '@angular/service-worker';
import { AppComponent } from './app.component';
import { ApiService } from './core/services/api.service';
import { AuthService } from './core/services/auth.service';
import { WebSocketService } from './core/services/websocket.service';
import { LoginComponent } from './features/auth/login/login.component';
import { FeedComponent } from './features/feed/feed.component';
import { SettingsComponent } from './features/settings/settings.component';
import { ChatWindowComponent } from './features/chat/chat-window/chat-window.component';
import { ChatRoom, Message } from './models/chat.model';
import { fakeApi, fakeAuth, fakeWs, otherUser, seriousViolations, settle, testPost, testUser } from '../testing/a11y';

/** The routed pages get a blank stand-in so the shell test only checks the shell. */
@Component({ selector: 'app-blank', template: '<h1>Page</h1>' })
class BlankComponent {}

const room: ChatRoom = {
  id: 7,
  room_type: 'direct',
  name: '',
  avatar: null,
  members: [
    { id: 1, user: testUser, role: 'member', last_read_at: null, joined_at: '2026-01-01T00:00:00Z' },
    { id: 2, user: otherUser, role: 'member', last_read_at: null, joined_at: '2026-01-01T00:00:00Z' },
  ],
  my_role: 'member',
  last_message: null,
  unread_count: 0,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

function message(id: number, mine: boolean, content: string): Message {
  return {
    id,
    room: 7,
    sender: mine ? testUser : otherUser,
    content,
    message_type: 'text',
    file_url: null,
    reply_to: null,
    reply_to_data: null,
    is_edited: false,
    edited_at: null,
    is_deleted: false,
    read_by_count: 0,
    duration_s: null,
    transcript: '',
    transcript_status: '',
    reactions: id === 2 ? [{ reaction: 'love', count: 1 }] : [],
    my_reaction: null,
    created_at: '2026-10-28T08:00:00Z',
    updated_at: '2026-10-28T08:00:00Z',
  };
}

function configure(responses: Record<string, unknown>, signedIn = true): void {
  TestBed.configureTestingModule({
    providers: [
      provideRouter([{ path: '**', component: BlankComponent }]),
      provideHttpClient(),
      provideHttpClientTesting(),
      provideServiceWorker('ngsw-worker.js', { enabled: false }),
      { provide: ApiService, useValue: fakeApi(responses) },
      { provide: AuthService, useValue: fakeAuth(signedIn ? testUser : null) },
      { provide: WebSocketService, useValue: fakeWs() },
    ],
  });
}

async function render<T>(component: Type<T>, setup?: (f: ComponentFixture<T>) => void) {
  const fixture = TestBed.createComponent(component);
  setup?.(fixture);
  fixture.detectChanges();
  await fixture.whenStable();
  await settle(50);
  fixture.detectChanges();
  return fixture;
}

async function expectNoSeriousViolations(fixture: ComponentFixture<unknown>): Promise<void> {
  const problems = await seriousViolations(fixture.nativeElement);
  expect(problems).withContext(problems.join('\n')).toEqual([]);
}

/**
 * Automated WCAG checks (axe-core) on the main screens with mocked services, in both
 * themes. Fails on serious or critical violations only; axe can't judge everything
 * (e.g. focus order), so these complement manual checks rather than replace them.
 */
describe('Accessibility (axe-core)', () => {
  const themes: ('light' | 'dark')[] = ['light', 'dark'];

  // axe samples colours at one instant: stop entrance animations and the theme
  // transition so it never measures a half-faded element.
  let freeze: HTMLStyleElement;
  beforeAll(() => {
    freeze = document.createElement('style');
    freeze.textContent = '*, *::before, *::after { animation: none !important; transition: none !important; }';
    document.head.appendChild(freeze);
  });
  afterAll(() => freeze.remove());
  afterEach(() => document.documentElement.removeAttribute('data-theme'));

  for (const theme of themes) {
    describe(`${theme} theme`, () => {
      beforeEach(() => document.documentElement.setAttribute('data-theme', theme));

      it('main shell (navbar, bottom navigation, skip link)', async () => {
        configure({ getUnreadCount: { unread_count: 3 } });
        const fixture = await render(AppComponent);
        expect(fixture.nativeElement.querySelector('.skip-link')).not.toBeNull();
        expect(fixture.nativeElement.querySelector('app-navbar')).not.toBeNull();
        await expectNoSeriousViolations(fixture);
      });

      it('login page', async () => {
        configure({}, false);
        const fixture = await render(LoginComponent);
        await expectNoSeriousViolations(fixture);
      });

      it('feed with posts and suggestions', async () => {
        configure({
          getFeed: { next: null, next_cursor: null, previous: null, results: [testPost(1), testPost(2)] },
          getSuggestions: [otherUser],
        });
        const fixture = await render(FeedComponent);
        expect(fixture.nativeElement.querySelectorAll('app-post-card').length).toBe(2);
        await expectNoSeriousViolations(fixture);
      });

      it('empty feed', async () => {
        configure({ getSuggestions: [] });
        const fixture = await render(FeedComponent);
        expect(fixture.nativeElement.querySelector('app-empty-state')).not.toBeNull();
        await expectNoSeriousViolations(fixture);
      });

      it('settings', async () => {
        configure({ getDataExports: [], getNotificationPreferences: {} });
        const fixture = await render(SettingsComponent);
        await expectNoSeriousViolations(fixture);
      });

      it('chat window', async () => {
        configure({
          getChatRoom: room,
          getRoomMessages: { count: 2, next: null, previous: null, results: [message(2, false, 'Sawubona!'), message(1, true, 'Hi there')] },
          markRoomRead: {},
          getRoomPresence: { online: [2] },
        });
        const fixture = await render(ChatWindowComponent, (f) => f.componentRef.setInput('roomId', '7'));
        expect(fixture.nativeElement.querySelectorAll('.message-row').length).toBe(2);
        await expectNoSeriousViolations(fixture);
      });
    });
  }
});
