import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { BehaviorSubject, Observable, tap } from 'rxjs';
import { User, AuthTokens, LoginResponse } from '../../models/user.model';
import { environment } from '../../../environments/environment';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly API = environment.apiUrl;
  private _currentUser = new BehaviorSubject<User | null>(this.loadUser());
  currentUser$ = this._currentUser.asObservable();

  constructor(private http: HttpClient, private router: Router) {}

  get currentUser(): User | null {
    return this._currentUser.value;
  }

  isLoggedIn(): boolean {
    return !!localStorage.getItem('access_token');
  }

  register(data: {
    username: string; email: string;
    first_name: string; last_name: string;
    password: string; password2: string;
  }): Observable<LoginResponse> {
    return this.http.post<LoginResponse>(`${this.API}/auth/register/`, data).pipe(
      tap((res) => this.storeSession(res))
    );
  }

  login(credentials: { username: string; password: string }): Observable<{ access: string; refresh: string }> {
    return this.http.post<{ access: string; refresh: string }>(`${this.API}/auth/login/`, credentials).pipe(
      tap((tokens) => {
        localStorage.setItem('access_token', tokens.access);
        localStorage.setItem('refresh_token', tokens.refresh);
        this.fetchMe().subscribe();
      })
    );
  }

  fetchMe(): Observable<User> {
    return this.http.get<User>(`${this.API}/auth/me/`).pipe(
      tap((user) => {
        this._currentUser.next(user);
        localStorage.setItem('user', JSON.stringify(user));
      })
    );
  }

  logout(): void {
    const refresh = localStorage.getItem('refresh_token');
    if (refresh) {
      this.http.post(`${this.API}/auth/token/blacklist/`, { refresh }).subscribe();
    }
    localStorage.clear();
    this._currentUser.next(null);
    this.router.navigate(['/login']);
  }

  getAccessToken(): string | null {
    return localStorage.getItem('access_token');
  }

  getRefreshToken(): string | null {
    return localStorage.getItem('refresh_token');
  }

  refreshAccessToken(): Observable<{ access: string }> {
    return this.http.post<{ access: string }>(`${this.API}/auth/token/refresh/`, {
      refresh: this.getRefreshToken(),
    }).pipe(
      tap((res) => localStorage.setItem('access_token', res.access))
    );
  }

  private storeSession(res: LoginResponse): void {
    localStorage.setItem('access_token', res.tokens.access);
    localStorage.setItem('refresh_token', res.tokens.refresh);
    localStorage.setItem('user', JSON.stringify(res.user));
    this._currentUser.next(res.user);
  }

  private loadUser(): User | null {
    const stored = localStorage.getItem('user');
    return stored ? JSON.parse(stored) : null;
  }
}
