import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { AssistantPanelComponent } from './assistant-panel.component';
import { safeCitationUrl, stepLabel } from './assistant.util';
import { WebSocketService } from '../../core/services/websocket.service';
import { AssistantProposal, AssistantRun } from '../../models/assistant.model';
import { environment } from '../../../environments/environment';

const api = environment.apiUrl;

function proposal(overrides: Partial<AssistantProposal> = {}): AssistantProposal {
  return {
    id: 7, run: 1, source: 'assistant', tool: 'send_message', status: 'pending', result: {}, error: '',
    preview: { action: 'message', text: 'Running late!', links: ['https://x.example'],
      to: [{ id: 2, username: 'sipho', name: 'Sipho' }], room: null },
    created_at: new Date().toISOString(), expires_at: new Date(Date.now() + 600_000).toISOString(),
    decided_at: null, ...overrides,
  };
}

function run(overrides: Partial<AssistantRun> = {}): AssistantRun {
  return {
    id: 1, request_text: 'tell sipho I am late', follow_up_of: null, path: 'draft_message',
    status: 'awaiting_approval', step_count: 2, total_tokens: 100, cost_usd: '0.001', answer: "Here's a draft.",
    citations: [], error: '', steps: [], proposals: [proposal()], created_at: '', updated_at: '', ...overrides,
  };
}

describe('assistant helpers', () => {
  it('only links to in-app content', () => {
    expect(safeCitationUrl('/posts/12')).toBe('/posts/12');
    expect(safeCitationUrl('/marketplace/3')).toBe('/marketplace/3');
    expect(safeCitationUrl('https://evil.example/posts/1')).toBeNull();
    expect(safeCitationUrl('javascript:alert(1)')).toBeNull();
    expect(safeCitationUrl('//evil.example')).toBeNull();
  });

  it('labels steps for people', () => {
    expect(stepLabel({ index: 0, kind: 'route', tool_name: '', is_error: false, created_at: '' }))
      .toBe('Understanding your request');
    expect(stepLabel({ index: 1, kind: 'tool', tool_name: 'send_message', is_error: false, created_at: '' }))
      .toContain('approval');
  });
});

describe('AssistantPanelComponent', () => {
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [AssistantPanelComponent],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting(), provideNoopAnimations()],
    });
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  function render() {
    const fixture = TestBed.createComponent(AssistantPanelComponent);
    fixture.detectChanges();
    backend.expectOne(`${api}/assistant/runs/`).flush([run()]);
    backend.expectOne((r) => r.url === `${api}/assistant/proposals/`).flush([]);
    fixture.detectChanges();
    return fixture;
  }

  it('shows exactly what will be sent and to whom, and approves only on click', () => {
    const fixture = render();
    const card: HTMLElement = fixture.nativeElement.querySelector('.proposal');
    expect(card.textContent).toContain('Running late!');
    expect(card.textContent).toContain('Sipho (@sipho)');
    expect(card.textContent).toContain('https://x.example');
    backend.expectNone(`${api}/assistant/proposals/7/approve/`);

    const approve = Array.from(card.querySelectorAll('button')).find((b) => b.textContent?.includes('Approve'))!;
    approve.click();
    const req = backend.expectOne(`${api}/assistant/proposals/7/approve/`);
    expect(req.request.method).toBe('POST');
    req.flush(proposal({ status: 'approved', result: { url: '/chat/3' } }));
    backend.expectOne(`${api}/assistant/runs/1/`).flush(run({
      status: 'done', answer: 'Done. Your message was sent.', proposals: [proposal({ status: 'approved' })],
    }));
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Done. Your message was sent.');
    expect(fixture.nativeElement.querySelector('.proposal-actions')).toBeNull();
  });

  it('refetches a run when the socket reports progress', () => {
    render();
    TestBed.inject(WebSocketService).assistantEvent$.next({ type: 'assistant.event', event: 'assistant.step',
      run_id: 1 });
    backend.expectOne(`${api}/assistant/runs/1/`).flush(run());
    TestBed.inject(WebSocketService).assistantEvent$.next({ type: 'assistant.event', event: 'assistant.step',
      run_id: 999 });
    backend.expectNone(`${api}/assistant/runs/999/`);
  });

  it('sends follow-ups with the previous finished run', () => {
    const fixture = TestBed.createComponent(AssistantPanelComponent);
    fixture.detectChanges();
    backend.expectOne(`${api}/assistant/runs/`).flush([run({ id: 4, status: 'done', proposals: [] })]);
    backend.expectOne((r) => r.url === `${api}/assistant/proposals/`).flush([]);
    const panel = fixture.componentInstance;
    panel.draft = 'and then?';
    panel.send();
    const req = backend.expectOne(`${api}/assistant/runs/`);
    expect(req.request.body).toEqual({ request: 'and then?', follow_up_of: 4 });
    req.flush(run({ id: 5, status: 'queued', proposals: [] }));
    panel.ngOnDestroy();
  });
});
