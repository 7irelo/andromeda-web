import axe from 'axe-core';
import { BehaviorSubject, Observable, Subject, of } from 'rxjs';
import { User } from '../app/models/user.model';
import { Post } from '../app/models/post.model';

/**
 * Runs axe-core (WCAG 2.0/2.1/2.2 A and AA rules plus best practices) against a rendered
 * fixture and returns a readable list of serious and critical violations.
 */
export async function seriousViolations(root: Element): Promise<string[]> {
  const results = await axe.run(root, {
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'] },
    resultTypes: ['violations'],
    rules: {
      // Experimental rule (enabled here only because we select by tag). It reads Material
      // icon ligatures ("menu", "chat") as visible text when the icon font isn't loaded,
      // as in Karma, so every labelled icon button would be a false positive.
      'label-content-name-mismatch': { enabled: false },
    },
  });
  return results.violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => {
      const nodes = v.nodes
        .slice(0, 6)
        .map((n) => `${n.target.join(' ')} -- ${n.any[0]?.message ?? n.failureSummary ?? ''}`);
      return `${v.impact} ${v.id}: ${v.help}\n  ${nodes.join('\n  ')}`;
    });
}

export const testUser: User = {
  id: 1,
  username: 'thandi',
  email: 'thandi@example.com',
  first_name: 'Thandi',
  last_name: 'Nkosi',
  full_name: 'Thandi Nkosi',
  bio: '',
  avatar_url: null,
  cover_photo_url: null,
  location: 'Durban',
  website: '',
  is_verified: false,
  friends_count: 12,
  posts_count: 3,
  created_at: '2026-01-01T00:00:00Z',
  privacy_profile: 'everyone',
  privacy_messages: 'friends',
  privacy_friend_requests: 'everyone',
  privacy_friends_list: 'friends',
  default_post_privacy: 'friends',
  show_online_status: true,
  searchable: true,
  email_verified: true,
};

export const otherUser: User = {
  ...testUser,
  id: 2,
  username: 'sipho',
  email: undefined,
  first_name: 'Sipho',
  last_name: 'Dlamini',
  full_name: 'Sipho Dlamini',
  is_friend: true,
};

export function testPost(id: number, overrides: Partial<Post> = {}): Post {
  return {
    id,
    author: otherUser,
    content: `Post number ${id} about #braai with friends`,
    post_type: 'text',
    privacy: 'public',
    image: null,
    video: null,
    link_url: '',
    link_title: '',
    link_description: '',
    link_image: '',
    group: null,
    page: null,
    likes_count: 4,
    comments_count: 1,
    shares_count: 0,
    shared_post: null,
    shared_post_data: null,
    is_edited: false,
    tags: [{ name: 'braai' }],
    media: [],
    my_reaction: null,
    is_saved: false,
    created_at: new Date(Date.now() - 3600_000).toISOString(),
    updated_at: new Date(Date.now() - 3600_000).toISOString(),
    ...overrides,
  };
}

const EMPTY_PAGE = { count: 0, next: null, previous: null, next_cursor: null, results: [] };
// Methods that return a plain array rather than a page.
const ARRAY_METHODS = new Set(['getAccessTokens']);

/**
 * ApiService stand-in: every method returns an observable of `responses[name]` (or an empty
 * page), so components render without HTTP. Pass the values a test cares about.
 */
export function fakeApi(responses: Record<string, unknown> = {}): unknown {
  return new Proxy({}, {
    get: (_target, prop: string) => {
      if (prop === 'then') return undefined; // not a promise
      return (..._args: unknown[]): Observable<unknown> => of(prop in responses ? responses[prop] : ARRAY_METHODS.has(prop) ? [] : EMPTY_PAGE);
    },
  });
}

/** AuthService stand-in for a signed-in (or signed-out) user. */
export function fakeAuth(user: User | null = testUser) {
  const current = new BehaviorSubject<User | null>(user);
  return {
    currentUser$: current.asObservable(),
    get currentUser() { return current.value; },
    isLoggedIn: () => !!current.value,
    getAccessToken: () => (current.value ? 'token' : null),
    login: () => of({ access: 'token', user: testUser }),
    completeMfaLogin: () => of({ access: 'token', user: testUser }),
    register: () => of({ access: 'token', user: testUser }),
    fetchMe: () => of(testUser),
    logout: () => undefined,
    logoutEverywhere: () => undefined,
    getSessions: () => of([]),
    getMfaStatus: () => of({ enabled: false, recovery_codes_left: 0 }),
    changePassword: () => of({}),
    deleteAccount: () => of({}),
    getWebSocketTicket: () => of('ticket'),
  };
}

/** WebSocketService stand-in: the real subjects, no sockets. */
export function fakeWs() {
  return {
    notification$: new Subject(),
    unreadCount$: new BehaviorSubject(3),
    feedNewPost$: new Subject<number>(),
    chatMessage$: new Subject(),
    typing$: new Subject(),
    chatError$: new Subject(),
    chatUnread$: new BehaviorSubject(2),
    messageUpdated$: new Subject(),
    reaction$: new Subject(),
    read$: new Subject(),
    status$: new Subject(),
    presence$: new Subject<number[]>(),
    roomUpdated$: new Subject<number>(),
    memberRemoved$: new Subject<number>(),
    chatReconnected$: new Subject<number>(),
    assistantEvent$: new Subject(),
    connectNotifications: () => undefined,
    disconnect: () => undefined,
    refreshChatUnread: () => undefined,
    connectChat: () => undefined,
    disconnectChat: () => undefined,
    sendChatMessage: () => true,
    sendTyping: () => undefined,
    markMessageRead: () => undefined,
    editMessage: () => true,
    deleteMessage: () => true,
    reactToMessage: () => undefined,
  };
}

/** Let async work (defer blocks, axe) settle. */
export function settle(ms = 0): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
