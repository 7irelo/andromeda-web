import { FeedEvent } from '../../models/post.model';

/** A post counts as seen after this long at least half on screen. */
export const SEEN_MS = 1000;
/** The server accepts at most this many events per batch. */
export const MAX_BATCH = 50;

/**
 * Keeps track of how long each feed post has been on screen and whether it
 * was opened, and hands out the changes since the last batch. Pure state, no
 * DOM: the feed component feeds it IntersectionObserver and click events.
 *
 * Dwell is cumulative per post and the server keeps the maximum it has seen,
 * so a batch that gets lost costs nothing once the next one arrives.
 */
export class DwellTracker {
  private readonly intersecting = new Set<number>();
  private readonly since = new Map<number, number>();
  private readonly dwell = new Map<number, number>();
  private readonly opened = new Set<number>();
  private readonly sent = new Map<number, { dwell: number; opened: boolean }>();
  private paused = false;

  constructor(private readonly now: () => number = () => performance.now()) {}

  /** The post went in or out of the ≥ 50% visible state. */
  visible(postId: number, isVisible: boolean): void {
    if (isVisible) {
      this.intersecting.add(postId);
      if (!this.paused && !this.since.has(postId)) this.since.set(postId, this.now());
    } else {
      this.intersecting.delete(postId);
      this.stop(postId);
    }
  }

  open(postId: number): void {
    this.opened.add(postId);
  }

  /** Page hidden: stop every clock (the observer doesn't fire while the tab is in the background). */
  pause(): void {
    this.paused = true;
    for (const id of [...this.since.keys()]) this.stop(id);
  }

  /** Page visible again: restart the clocks of posts still on screen. */
  resume(): void {
    this.paused = false;
    const t = this.now();
    for (const id of this.intersecting) if (!this.since.has(id)) this.since.set(id, t);
  }

  /** Events that changed since the last call: newly seen or longer-seen posts, and opens. */
  drain(max = MAX_BATCH): FeedEvent[] {
    const t = this.now();
    const ids = new Set<number>([...this.dwell.keys(), ...this.since.keys(), ...this.opened]);
    const events: FeedEvent[] = [];
    for (const id of ids) {
      if (events.length >= max) break;
      const start = this.since.get(id);
      const total = Math.round((this.dwell.get(id) ?? 0) + (start === undefined ? 0 : t - start));
      const last = this.sent.get(id) ?? { dwell: 0, opened: false };
      const isOpened = this.opened.has(id);
      const moreDwell = total >= SEEN_MS && total > last.dwell;
      const newOpen = isOpened && !last.opened;
      if (!moreDwell && !newOpen) continue;
      const event: FeedEvent = { post: id };
      if (total >= SEEN_MS) event.dwell_ms = total;
      if (isOpened) event.opened = true;
      events.push(event);
      this.sent.set(id, { dwell: Math.max(last.dwell, total), opened: last.opened || isOpened });
    }
    return events;
  }

  private stop(postId: number): void {
    const start = this.since.get(postId);
    if (start === undefined) return;
    this.since.delete(postId);
    this.dwell.set(postId, (this.dwell.get(postId) ?? 0) + (this.now() - start));
  }
}
