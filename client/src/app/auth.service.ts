import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { tap } from 'rxjs/operators';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private isAuthenticated = false;

  constructor(private http: HttpClient) {}

  login(credentials: {username: string, password: string}): Observable<any> {
    return this.http.post('http://localhost:8000/api/login', credentials, { withCredentials: true })
      .pipe(
        tap(response => {
          this.isAuthenticated = true;
        })
      );
  }

  logout(): Observable<any> {
    return this.http.post('http://localhost:8000/api/logout', {}, { withCredentials: true })
      .pipe(
        tap(response => {
          this.isAuthenticated = false;
        })
      );
  }

  checkAuth(): Observable<boolean> {
    // Implement a real check here, for simplicity, we use a dummy check
    return of(this.isAuthenticated);
  }
}
