import { TestBed } from '@angular/core/testing';
import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { authInterceptor } from './auth.interceptor';
import { AuthService } from '../services/auth.service';
import { environment } from '../../../environments/environment';

describe('authInterceptor', () => {
  let http: HttpClient;
  let backend: HttpTestingController;
  let auth: AuthService;
  const api = environment.apiUrl;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
    auth = TestBed.inject(AuthService);
    (auth as unknown as { accessToken: string }).accessToken = 'access-1';
  });

  afterEach(() => backend.verify());

  it('attaches the bearer token to API calls', () => {
    http.get(`${api}/posts/`).subscribe();
    expect(backend.expectOne(`${api}/posts/`).request.headers.get('Authorization')).toBe('Bearer access-1');
  });

  it('never sends the token to third-party hosts', () => {
    http.get('https://evil.example/collect').subscribe();
    expect(backend.expectOne('https://evil.example/collect').request.headers.has('Authorization')).toBeFalse();
  });

  it('refreshes once on 401 and retries with the new token', () => {
    http.get(`${api}/me/`).subscribe();
    backend.expectOne(`${api}/me/`).flush({}, { status: 401, statusText: 'Unauthorized' });
    const refresh = backend.expectOne(`${api}/auth/token/refresh/`);
    expect(refresh.request.withCredentials).toBeTrue();
    expect(refresh.request.body).toEqual({});  // the refresh token travels only in the HttpOnly cookie
    refresh.flush({ access: 'access-2' });
    expect(backend.expectOne(`${api}/me/`).request.headers.get('Authorization')).toBe('Bearer access-2');
  });

  it('does not try to refresh when the refresh call itself fails', () => {
    http.post(`${api}/auth/token/refresh/`, {}).subscribe({ error: () => undefined });
    backend.expectOne(`${api}/auth/token/refresh/`).flush({}, { status: 401, statusText: 'Unauthorized' });
    backend.expectNone(`${api}/auth/token/refresh/`);
    backend.match(`${api}/auth/logout/`);
  });
});

describe('AuthService session storage', () => {
  it('keeps tokens out of localStorage and sessionStorage', () => {
    TestBed.configureTestingModule({ providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()] });
    const auth = TestBed.inject(AuthService);
    const backend = TestBed.inject(HttpTestingController);
    localStorage.clear();
    sessionStorage.clear();
    auth.login({ username: 'a', password: 'b' }).subscribe();
    backend.expectOne(`${environment.apiUrl}/auth/login/`).flush({ access: 'secret-token', user: { id: 1 } });
    const stored = JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage });
    expect(stored).not.toContain('secret-token');
    expect(auth.getAccessToken()).toBe('secret-token');
  });
});
