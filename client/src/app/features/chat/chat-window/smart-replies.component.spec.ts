import { TestBed, fakeAsync, tick } from '@angular/core/testing';
import { SimpleChange } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { BehaviorSubject } from 'rxjs';
import { SmartRepliesComponent } from './smart-replies.component';
import { AuthService } from '../../../core/services/auth.service';
import { environment } from '../../../../environments/environment';
import { User } from '../../../models/user.model';

describe('SmartRepliesComponent', () => {
  const api = environment.apiUrl;
  const suggestUrl = `${api}/chats/rooms/7/suggest_replies/`;
  const feedbackUrl = `${api}/chats/rooms/7/reply_feedback/`;
  const SUGGESTIONS = [{ id: 'a'.repeat(64), text: 'Sounds good!' }, { id: 'b'.repeat(64), text: 'What time?' }];
  let backend: HttpTestingController;

  function setup(user: Partial<User> | null = { id: 1, ai_opt_out: false }) {
    TestBed.configureTestingModule({
      imports: [SmartRepliesComponent],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting(), provideNoopAnimations()],
    });
    backend = TestBed.inject(HttpTestingController);
    const auth = TestBed.inject(AuthService);
    (auth as unknown as { _currentUser: BehaviorSubject<User | null> })._currentUser.next(user as User);
    const fixture = TestBed.createComponent(SmartRepliesComponent);
    fixture.componentInstance.roomId = 7;
    fixture.detectChanges();
    return fixture;
  }

  function setDraft(c: SmartRepliesComponent, draft: string) {
    const previous = c.draft;
    c.draft = draft;
    c.ngOnChanges({ draft: new SimpleChange(previous, draft, false) });
  }

  afterEach(() => backend.verify());

  it('is hidden when the user has turned AI off', () => {
    const fixture = setup({ id: 1, ai_opt_out: true });
    expect(fixture.nativeElement.querySelector('.smart-replies')).toBeNull();
    fixture.componentInstance.request();
    backend.expectNone(suggestUrl);
  });

  it('fills the input on tap without sending, then logs accepted for a verbatim send', () => {
    const fixture = setup();
    const c = fixture.componentInstance;
    const picked: string[] = [];
    c.pick.subscribe((t) => picked.push(t));
    c.request();
    backend.expectOne(suggestUrl).flush({ suggestions: SUGGESTIONS, variant: 'haiku', anchor_id: 3 });
    fixture.detectChanges();
    const chips = fixture.nativeElement.querySelectorAll('button.chip');
    expect(chips.length).toBe(2);
    (chips[1] as HTMLButtonElement).click();
    expect(picked).toEqual(['What time?']);
    setDraft(c, 'What time?');
    c.noteSent('What time? ');
    const fb = backend.expectOne(feedbackUrl);
    expect(fb.request.body).toEqual({ action: 'accepted', suggestion_ids: ['b'.repeat(64)] });
    fb.flush({ recorded: 1 });
  });

  it('logs edited when the suggestion was changed before sending', () => {
    const c = setup().componentInstance;
    c.request();
    backend.expectOne(suggestUrl).flush({ suggestions: SUGGESTIONS, variant: 'luna', anchor_id: 3 });
    c.choose(SUGGESTIONS[0]);
    setDraft(c, 'Sounds good!');
    setDraft(c, 'Sounds good, see you then!');
    c.noteSent('Sounds good, see you then!');
    expect(backend.expectOne(feedbackUrl).request.body.action).toBe('edited');
  });

  it('cancels the request in flight when the user starts typing', () => {
    const c = setup().componentInstance;
    c.request();
    const req = backend.expectOne(suggestUrl);
    setDraft(c, 'I was going to say');
    expect(req.cancelled).toBeTrue();
    expect(c.suggestions).toEqual([]);
  });

  it('dismiss logs every shown suggestion and sending without a pick logs nothing', () => {
    const c = setup().componentInstance;
    c.request();
    backend.expectOne(suggestUrl).flush({ suggestions: SUGGESTIONS, variant: 'haiku', anchor_id: 3 });
    c.dismiss();
    expect(backend.expectOne(feedbackUrl).request.body).toEqual(
      { action: 'dismissed', suggestion_ids: SUGGESTIONS.map((s) => s.id) });
    c.noteSent('my own words');
    backend.expectNone(feedbackUrl);
  });

  it('suggests automatically after a new incoming message, debounced and rate-limited', fakeAsync(() => {
    const c = setup().componentInstance;
    const bump = () => {
      c.incomingTick++;
      c.ngOnChanges({ incomingTick: new SimpleChange(c.incomingTick - 1, c.incomingTick, false) });
    };
    bump();
    bump();
    tick(1000);
    backend.expectNone(suggestUrl);
    tick(600);
    backend.expectOne(suggestUrl).flush({ suggestions: [], variant: 'haiku', anchor_id: 3 });
    expect(c.note).toBe('No suggestions for this one.');
    bump();
    tick(2000);
    backend.expectNone(suggestUrl);  // one automatic request a minute at most
  }));

  it('does not suggest automatically while the user is typing', fakeAsync(() => {
    const c = setup().componentInstance;
    setDraft(c, 'typing…');
    c.incomingTick = 1;
    c.ngOnChanges({ incomingTick: new SimpleChange(0, 1, false) });
    tick(2000);
    backend.expectNone(suggestUrl);
    expect(c.loading).toBeFalse();
  }));

  it('stops offering suggestions after the allowance is used up', () => {
    const fixture = setup();
    const c = fixture.componentInstance;
    c.request();
    backend.expectOne(suggestUrl).flush({ detail: 'slow down' }, { status: 429, statusText: 'Too Many Requests' });
    fixture.detectChanges();
    expect(c.unavailable).toBeTrue();
    expect(fixture.nativeElement.querySelector('button.chip.ask')).toBeNull();
    c.request();
    backend.expectNone(suggestUrl);
  });
});
