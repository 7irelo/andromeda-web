import { DwellTracker, MAX_BATCH, SEEN_MS } from './dwell-tracker';

describe('DwellTracker', () => {
  let clock: number;
  let tracker: DwellTracker;

  beforeEach(() => {
    clock = 0;
    tracker = new DwellTracker(() => clock);
  });

  it('reports a post only once it has been visible for a second', () => {
    tracker.visible(1, true);
    clock = SEEN_MS - 1;
    expect(tracker.drain()).toEqual([]);
    clock = SEEN_MS + 200;
    expect(tracker.drain()).toEqual([{ post: 1, dwell_ms: SEEN_MS + 200 }]);
  });

  it('accumulates dwell across visits and only resends when it grows', () => {
    tracker.visible(1, true);
    clock = 600;
    tracker.visible(1, false);
    clock = 5000;
    tracker.visible(1, true);
    clock = 5600;
    expect(tracker.drain()).toEqual([{ post: 1, dwell_ms: 1200 }]);
    tracker.visible(1, false);
    expect(tracker.drain()).toEqual([]);
  });

  it('reports opens even for a quick glance, once', () => {
    tracker.visible(2, true);
    clock = 100;
    tracker.open(2);
    expect(tracker.drain()).toEqual([{ post: 2, opened: true }]);
    expect(tracker.drain()).toEqual([]);
  });

  it('stops the clocks while the page is hidden', () => {
    tracker.visible(3, true);
    clock = 800;
    tracker.pause();
    clock = 60000;
    expect(tracker.drain()).toEqual([]);
    tracker.resume();
    clock = 60300;
    expect(tracker.drain()).toEqual([{ post: 3, dwell_ms: 1100 }]);
  });

  it('caps a batch and keeps the rest for the next one', () => {
    for (let id = 1; id <= MAX_BATCH + 5; id++) tracker.open(id);
    expect(tracker.drain().length).toBe(MAX_BATCH);
    expect(tracker.drain().length).toBe(5);
  });
});
