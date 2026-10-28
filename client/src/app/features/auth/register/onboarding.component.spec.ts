import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { ApiService } from '../../../core/services/api.service';
import { Group } from '../../../models/group.model';
import { OnboardingComponent } from './onboarding.component';

function group(id: number, name: string, extra: Partial<Group> = {}): Group {
  return { id, name, privacy: 'public', members_count: 10, is_member: false, cover_photo: null, ...extra } as Group;
}

describe('OnboardingComponent', () => {
  let api: jasmine.SpyObj<ApiService>;

  beforeEach(() => {
    api = jasmine.createSpyObj<ApiService>('ApiService', ['getGroups', 'joinGroup', 'createPost']);
    TestBed.configureTestingModule({ providers: [{ provide: ApiService, useValue: api }] });
  });

  it('searches groups for each chosen interest and merges the results', () => {
    api.getGroups.and.callFake((params?: Record<string, string>) => of({
      count: 2, next: null, previous: null,
      results: params?.['search'] === 'music'
        ? [group(1, 'Durban Music'), group(2, 'Jazz Lovers')]
        : [group(2, 'Jazz Lovers'), group(3, 'Food Club'), group(4, 'Secret', { privacy: 'secret' })],
    }) as never);
    const c = TestBed.createComponent(OnboardingComponent).componentInstance;
    c.toggle('music');
    c.toggle('food');
    c.goGroups();
    expect(api.getGroups).toHaveBeenCalledWith({ search: 'music' });
    expect(api.getGroups).toHaveBeenCalledWith({ search: 'food' });
    expect(c.groups().map((g) => g.id)).toEqual([1, 2, 3]);
  });

  it('falls back to open groups when no interest matches', () => {
    api.getGroups.and.callFake((params?: Record<string, string>) => of({
      count: 1, next: null, previous: null, results: params ? [] : [group(9, 'Andromeda Newcomers')],
    }) as never);
    const c = TestBed.createComponent(OnboardingComponent).componentInstance;
    c.toggle('tech');
    c.goGroups();
    expect(c.groups().map((g) => g.id)).toEqual([9]);
  });

  it('drafts a first post from the chosen interests, and posts it', () => {
    api.createPost.and.returnValue(of({ id: 1 } as unknown as never) as never);
    const fixture = TestBed.createComponent(OnboardingComponent);
    const c = fixture.componentInstance;
    let finished = false;
    c.done.subscribe(() => (finished = true));
    c.toggle('music');
    c.toggle('travel');
    c.goPost();
    expect(c.draft).toContain('music and travel');
    c.publish();
    const body = api.createPost.calls.mostRecent().args[0] as FormData;
    expect(body.get('content')).toBe(c.draft.trim());
    expect(finished).toBeTrue();
  });
});
