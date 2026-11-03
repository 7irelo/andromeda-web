import { closeMessage, nextStartTime, pcm16ToFloat } from './voice-playback';

describe('voice playback helpers', () => {
  it('decodes PCM16 to floats', () => {
    const out = pcm16ToFloat(new Int16Array([0, 16384, -32768]).buffer);
    expect(Array.from(out)).toEqual([0, 0.5, -1]);
  });

  it('queues chunks back to back', () => {
    expect(nextStartTime(10, 12)).toBe(12);
  });

  it('restarts just ahead of now after running dry', () => {
    expect(nextStartTime(10, 4)).toBeCloseTo(10.05);
  });

  it('explains why a session closed', () => {
    expect(closeMessage(4403)).toContain('AI features');
    expect(closeMessage(1006)).toContain('lost');
  });
});
