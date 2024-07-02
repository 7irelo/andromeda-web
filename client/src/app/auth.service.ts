import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of, throwError } from 'rxjs';
import { tap, catchError } from 'rxjs/operators';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private apiUrl = 'http://localhost:8000/api';
  private isAuthenticated = false;
  private username: string | null = null;

  constructor(private http: HttpClient) {}

  /**
   * Logs in the user with the provided credentials.
   * @param credentials - The user's login credentials.
   * @returns An observable of the login response.
   */
  login(credentials: { username: string, password: string }): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/login`, credentials, { withCredentials: true })
      .pipe(
        tap(response => {
          this.isAuthenticated = true;
          this.username = response.username; // Assuming response contains username
        }),
        catchError(this.handleError('login', []))
      );
  }

  /**
   * Logs out the user.
   * @returns An observable of the logout response.
   */
  logout(): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/logout`, {}, { withCredentials: true })
      .pipe(
        tap(() => {
          this.isAuthenticated = false;
          this.username = null;
        }),
        catchError(this.handleError('logout', []))
      );
  }

  /**
   * Registers a new user.
   * @param userData - The user's registration data.
   * @returns An observable of the registration response.
   */
  register(userData: any): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/register`, userData, { withCredentials: true })
      .pipe(
        catchError(this.handleError('register', []))
      );
  }

  /**
   * Checks if the user is authenticated.
   * @returns An observable of the authentication status.
   */
  checkAuth(): Observable<boolean> {
    return of(this.isAuthenticated);
  }

  /**
   * Gets the authenticated user's username.
   * @returns The authenticated user's username or null if not authenticated.
   */
  getAuthenticatedUsername(): string | null {
    return this.username;
  }

  /**
   * Handles HTTP operation failures.
   * @param operation - The name of the operation that failed.
   * @param result - Optional value to return as the observable result.
   * @returns A function that returns an observable of the provided result.
   */
  private handleError<T>(operation = 'operation', result?: T) {
    return (error: any): Observable<T> => {
      console.error(`${operation} failed: ${error.message}`);
      return throwError(result as T);
    };
  }
}
