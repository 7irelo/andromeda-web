/** Decoding and scheduling for streamed PCM16 replies, kept apart from the browser's audio objects. */

export function pcm16ToFloat(buffer: ArrayBuffer): Float32Array {
  const samples = new Int16Array(buffer);
  const out = new Float32Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    out[i] = samples[i] / 0x8000;
  }
  return out;
}

/** When the next chunk should start: straight after the last one, or shortly from now if playback ran dry. */
export function nextStartTime(now: number, scheduledUntil: number, leadSeconds = 0.05): number {
  return Math.max(now + leadSeconds, scheduledUntil);
}

export function closeMessage(code: number): string {
  switch (code) {
    case 4403: return 'Voice is off because you turned off AI features in your settings.';
    case 4409: return 'You already have a voice conversation open in another tab.';
    case 4503: return 'Voice is unavailable right now.';
    case 4000: return 'This voice conversation has ended. You can start another one.';
    default: return 'The voice connection was lost.';
  }
}
