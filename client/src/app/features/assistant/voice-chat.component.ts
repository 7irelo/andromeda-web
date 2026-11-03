import { ChangeDetectorRef, Component, OnDestroy } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { AuthService } from '../../core/services/auth.service';
import { environment } from '../../../environments/environment';
import { closeMessage, nextStartTime, pcm16ToFloat } from './voice-playback';

const SAMPLE_RATE = 24000;

type VoiceState = 'idle' | 'connecting' | 'live';

/** Hands-free conversation: microphone to server as PCM16, replies played back as they arrive. */
@Component({
  selector: 'app-voice-chat',
  imports: [MatIconModule],
  template: `
    <div class="voice">
      <button type="button" class="talk" [class.live]="state === 'live'" [disabled]="state === 'connecting'"
              (click)="toggle()" [attr.aria-pressed]="state === 'live'">
        <mat-icon aria-hidden="true">{{ state === 'live' ? 'stop' : 'mic' }}</mat-icon>
        {{ state === 'live' ? 'End voice chat' : state === 'connecting' ? 'Connecting…' : 'Talk to the assistant' }}
      </button>
      @if (state === 'live') {
        <p class="hint">Listening. Start talking at any time to interrupt. Audio goes to our speech providers
          and isn't kept. Voice can look things up, but posting happens here in the panel.</p>
      }
      @if (heard) { <p class="line"><strong>You:</strong> {{ heard }}</p> }
      @if (reply) { <p class="line" aria-live="polite"><strong>Assistant:</strong> {{ reply }}</p> }
      @if (message) { <p class="message" role="status">{{ message }}</p> }
    </div>
  `,
  styles: [`
    .voice { padding: 8px 12px; border-bottom: 1px solid var(--border, rgba(127, 127, 127, .3)); }
    .talk { display: inline-flex; align-items: center; gap: 6px; min-height: 44px; padding: 0 14px; cursor: pointer;
      border-radius: 22px; border: 1px solid var(--border, rgba(127, 127, 127, .4)); background: transparent; color: inherit; }
    .talk.live { background: var(--primary-strong, #1d4ed8); color: #fff; }
    .hint, .line, .message { margin: 8px 0 0; font-size: 13px; }
  `],
})
export class VoiceChatComponent implements OnDestroy {
  state: VoiceState = 'idle';
  heard = '';
  reply = '';
  message = '';

  private ws?: WebSocket;
  private context?: AudioContext;
  private stream?: MediaStream;
  private scheduledUntil = 0;
  private playing = new Set<AudioBufferSourceNode>();

  constructor(private auth: AuthService, private cdr: ChangeDetectorRef) {}

  toggle(): void {
    if (this.state === 'live') {
      this.stop();
    } else if (this.state === 'idle') {
      void this.start();
    }
  }

  private async start(): Promise<void> {
    this.state = 'connecting';
    this.message = '';
    this.heard = '';
    this.reply = '';
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
      });
      this.context = new AudioContext({ sampleRate: SAMPLE_RATE });
      await this.context.audioWorklet.addModule('assets/voice-capture.worklet.js');
    } catch {
      this.finish('Andromeda needs microphone access for voice chat.');
      return;
    }
    this.auth.getWebSocketTicket().subscribe({
      next: (ticket) => this.connect(ticket),
      error: () => this.finish('Voice is unavailable right now.'),
    });
  }

  private connect(ticket: string): void {
    const ws = new WebSocket(`${environment.wsUrl}/voice/?ticket=${encodeURIComponent(ticket)}`);
    ws.binaryType = 'arraybuffer';
    this.ws = ws;
    ws.onmessage = (event) => {
      if (typeof event.data === 'string') {
        this.onEvent(JSON.parse(event.data));
      } else {
        this.play(event.data);
      }
    };
    ws.onclose = (event) => {
      if (this.ws === ws) {
        this.finish(event.code === 1000 ? '' : closeMessage(event.code));
      }
    };
  }

  private onEvent(event: { type: string; text?: string; final?: boolean; code?: string }): void {
    switch (event.type) {
      case 'ready':
        this.startCapture();
        this.state = 'live';
        break;
      case 'transcript':
        if (this.reply && event.final) this.reply = '';
        this.heard = event.text ?? '';
        break;
      case 'reply':
        this.reply = `${this.reply} ${event.text ?? ''}`.trim();
        break;
      case 'interrupt':
        this.silence();
        break;
      case 'error':
        this.message = 'The assistant had trouble replying. Please try again.';
        break;
    }
    this.cdr.markForCheck();
    this.cdr.detectChanges();
  }

  private startCapture(): void {
    if (!this.context || !this.stream) return;
    const source = this.context.createMediaStreamSource(this.stream);
    const capture = new AudioWorkletNode(this.context, 'voice-capture');
    capture.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(event.data);
      }
    };
    source.connect(capture);
  }

  private play(data: ArrayBuffer): void {
    if (!this.context) return;
    const samples = pcm16ToFloat(data);
    if (!samples.length) return;
    const buffer = this.context.createBuffer(1, samples.length, SAMPLE_RATE);
    buffer.copyToChannel(samples as Float32Array<ArrayBuffer>, 0);
    const node = this.context.createBufferSource();
    node.buffer = buffer;
    node.connect(this.context.destination);
    const startAt = nextStartTime(this.context.currentTime, this.scheduledUntil);
    node.start(startAt);
    this.scheduledUntil = startAt + buffer.duration;
    this.playing.add(node);
    node.onended = () => this.playing.delete(node);
  }

  private silence(): void {
    this.playing.forEach((node) => {
      node.onended = null;
      node.stop();
    });
    this.playing.clear();
    this.scheduledUntil = 0;
  }

  private stop(): void {
    this.finish('');
  }

  private finish(message: string): void {
    const ws = this.ws;
    this.ws = undefined;
    ws?.close();
    this.silence();
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = undefined;
    void this.context?.close();
    this.context = undefined;
    this.state = 'idle';
    this.message = message;
    this.cdr.markForCheck();
    this.cdr.detectChanges();
  }

  ngOnDestroy(): void {
    const ws = this.ws;
    this.ws = undefined;
    ws?.close();
    this.silence();
    this.stream?.getTracks().forEach((track) => track.stop());
    void this.context?.close();
  }
}
