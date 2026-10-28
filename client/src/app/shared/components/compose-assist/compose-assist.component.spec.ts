import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { BehaviorSubject } from 'rxjs';
import { ComposeAssistComponent } from './compose-assist.component';
import { AuthService } from '../../../core/services/auth.service';
import { environment } from '../../../../environments/environment';
import { User } from '../../../models/user.model';

describe('ComposeAssistComponent', () => {
  const url = `${environment.apiUrl}/posts/compose-assist/`;
  let backend: HttpTestingController;

  function setup(user: Partial<User> = { id: 1, ai_opt_out: false }) {
    TestBed.configureTestingModule({
      imports: [ComposeAssistComponent],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting(), provideNoopAnimations()],
    });
    backend = TestBed.inject(HttpTestingController);
    (TestBed.inject(AuthService) as unknown as { _currentUser: BehaviorSubject<User | null> })
      ._currentUser.next(user as User);
    const fixture = TestBed.createComponent(ComposeAssistComponent);
    fixture.componentInstance.text = ' hello frends ';
    fixture.componentInstance.kind = 'listing';
    fixture.detectChanges();
    return fixture;
  }

  afterEach(() => backend.verify());

  it('shows the suggestion and only replaces the draft on Accept', () => {
    const fixture = setup();
    const c = fixture.componentInstance;
    const accepted: string[] = [];
    c.accepted.subscribe((t) => accepted.push(t));
    c.run('translate', 'zu');
    const req = backend.expectOne(url);
    expect(req.request.body).toEqual({ text: 'hello frends', action: 'translate', language: 'zu', kind: 'listing' });
    req.flush({ text: 'Sawubona bangane <b>!</b>', truncated: false });
    fixture.detectChanges();
    expect(accepted).toEqual([]);
    // Rendered as text, never as HTML.
    expect(fixture.nativeElement.querySelector('.assist-text').textContent).toContain('<b>!</b>');
    c.accept();
    expect(accepted).toEqual(['Sawubona bangane <b>!</b>']);
    expect(c.suggestion).toBeNull();
  });

  it('discard drops the suggestion without touching the draft', () => {
    const c = setup().componentInstance;
    const accepted: string[] = [];
    c.accepted.subscribe((t) => accepted.push(t));
    c.run('shorter');
    backend.expectOne(url).flush({ text: 'Hi', truncated: false });
    c.discard();
    expect(accepted).toEqual([]);
    expect(c.suggestion).toBeNull();
  });

  it('is hidden for users who turned AI off, and needs a draft', () => {
    const fixture = setup({ id: 1, ai_opt_out: true });
    expect(fixture.nativeElement.querySelector('.assist-btn')).toBeNull();
    fixture.componentInstance.text = '   ';
    expect(fixture.componentInstance.canAssist).toBeFalse();
    fixture.componentInstance.run('grammar');
    backend.expectNone(url);
  });

  it('shows the server message when the allowance is used up', () => {
    const c = setup().componentInstance;
    c.run('grammar');
    backend.expectOne(url).flush({ detail: "You've used today's AI allowance." },
      { status: 429, statusText: 'Too Many Requests' });
    expect(c.error).toContain('allowance');
    expect(c.loading).toBeFalse();
  });
});
