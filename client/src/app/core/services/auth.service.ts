import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { BehaviorSubject, Observable, catchError, finalize, map, of, shareReplay, switchMap, tap } from 'rxjs';
import { DeviceSession, MfaChallenge, MfaSetup, MfaStatus, User, SessionResponse } from '../../models/user.model';
import { environment } from '../../../environments/environment';

/**
 * Session handling.
 *
 * - The access token lives only in memory, never in localStorage, so a script
 *   injection can't harvest a long-lived credential.
 * - The refresh token is an HttpOnly, SameSite=Strict cookie set by the API and
 *   scoped to /api/auth/. JavaScript never sees it.
 * - On page load, `restoreSession()` exchanges the cookie for a fresh access token.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly API = environment.apiUrl;
  private accessToken: string | null = null;
  private refreshInFlight$: Observable<string> | null = null;
  private _currentUser = new BehaviorSubject<User | null>(null);
  currentUser$ = this._currentUser.asObservable();

  constructor(private http: HttpClient, private router: Router) {}

  get currentUser(): User | null {
    return this._currentUser.value;
  }

  isLoggedIn(): boolean {
    return !!this.accessToken && !!this._currentUser.value;
  }

  getAccessToken(): string | null {
    return this.accessToken;
  }

  register(data: {
    username: string; email: string;
    first_name: string; last_name: string;
    password: string; password2: string;
  }): Observable<SessionResponse> {
    return this.http
      .post<SessionResponse>(`${this.API}/auth/register/`, data, { withCredentials: true })
      .pipe(tap((res) => this.startSession(res)));
  }

  /** Resolves to a session, or to a challenge when the account has two-factor sign-in on. */
  login(credentials: { username: string; password: string }): Observable<SessionResponse | MfaChallenge> {
    return this.http
      .post<SessionResponse | MfaChallenge>(`${this.API}/auth/login/`, credentials, { withCredentials: true })
      .pipe(tap((res) => {
        if (!('mfa_required' in res)) {
          this.startSession(res);
        }
      }));
  }

  completeMfaLogin(mfa_token: string, code: string): Observable<SessionResponse> {
    return this.http
      .post<SessionResponse>(`${this.API}/auth/login/mfa/`, { mfa_token, code }, { withCredentials: true })
      .pipe(tap((res) => this.startSession(res)));
  }

  // ── Devices, two-factor and email verification ─────────────────────────

  getSessions(): Observable<DeviceSession[]> {
    return this.http.get<DeviceSession[]>(`${this.API}/auth/sessions/`, { withCredentials: true });
  }

  revokeSession(id: string): Observable<void> {
    return this.http.delete<void>(`${this.API}/auth/sessions/${encodeURIComponent(id)}/`);
  }

  getMfaStatus(): Observable<MfaStatus> {
    return this.http.get<MfaStatus>(`${this.API}/auth/mfa/`);
  }

  startMfaSetup(password: string): Observable<MfaSetup> {
    return this.http.post<MfaSetup>(`${this.API}/auth/mfa/setup/`, { password });
  }

  enableMfa(code: string): Observable<{ enabled: boolean; recovery_codes: string[] }> {
    return this.http.post<{ enabled: boolean; recovery_codes: string[] }>(
      `${this.API}/auth/mfa/enable/`, { code }, { withCredentials: true });
  }

  disableMfa(password: string, code: string): Observable<{ enabled: boolean }> {
    return this.http.post<{ enabled: boolean }>(`${this.API}/auth/mfa/disable/`, { password, code });
  }

  verifyEmail(token: string): Observable<{ detail: string }> {
    return this.http.post<{ detail: string }>(`${this.API}/auth/email/verify/`, { token });
  }

  resendVerification(): Observable<unknown> {
    return this.http.post(`${this.API}/auth/email/resend/`, {});
  }

  /** Called once at startup: silently resume a session from the refresh cookie. */
  restoreSession(): Observable<boolean> {
    return this.refreshAccessToken().pipe(
      switchMap(() => this.fetchMe()),
      map(() => true),
      catchError(() => {
        this.clearSession();
        return of(false);
      })
    );
  }

  fetchMe(): Observable<User> {
    return this.http.get<User>(`${this.API}/auth/me/`).pipe(tap((user) => this._currentUser.next(user)));
  }

  /** Concurrent 401s share a single refresh request (the cookie rotates on each use). */
  refreshAccessToken(): Observable<string> {
    if (!this.refreshInFlight$) {
      this.refreshInFlight$ = this.http
        .post<{ access: string }>(`${this.API}/auth/token/refresh/`, {}, { withCredentials: true })
        .pipe(
          map((res) => res.access),
          tap((access) => (this.accessToken = access)),
          finalize(() => (this.refreshInFlight$ = null)),
          shareReplay(1)
        );
    }
    return this.refreshInFlight$;
  }

  /** One-time ticket for authenticating a WebSocket handshake. */
  getWebSocketTicket(): Observable<string> {
    return this.http.post<{ ticket: string }>(`${this.API}/auth/ws-ticket/`, {}).pipe(map((r) => r.ticket));
  }

  changePassword(current_password: string, new_password: string): Observable<SessionResponse> {
    return this.http
      .post<SessionResponse>(`${this.API}/auth/password/change/`, { current_password, new_password }, { withCredentials: true })
      .pipe(tap((res) => this.startSession(res)));
  }

  requestPasswordReset(email: string): Observable<unknown> {
    return this.http.post(`${this.API}/auth/password/reset/`, { email });
  }

  confirmPasswordReset(uid: string, token: string, new_password: string): Observable<unknown> {
    return this.http.post(`${this.API}/auth/password/reset/confirm/`, { uid, token, new_password });
  }

  deleteAccount(password: string): Observable<void> {
    return this.http
      .post<void>(`${this.API}/auth/me/delete/`, { password }, { withCredentials: true })
      .pipe(tap(() => this.endSession()));
  }

  logoutEverywhere(): void {
    this.http.post(`${this.API}/auth/logout-all/`, {}, { withCredentials: true })
      .pipe(catchError(() => of(null)))
      .subscribe(() => this.endSession());
  }

  logout(): void {
    this.http.post(`${this.API}/auth/logout/`, {}, { withCredentials: true })
      .pipe(catchError(() => of(null)))
      .subscribe();
    this.endSession();
  }

  /** Drop local state without calling the API (e.g. the refresh cookie already expired). */
  clearSession(): void {
    this.accessToken = null;
    this._currentUser.next(null);
  }

  private endSession(): void {
    this.clearSession();
    this.router.navigate(['/login']);
  }

  private startSession(res: SessionResponse): void {
    this.accessToken = res.access;
    this._currentUser.next(res.user);
  }
}
