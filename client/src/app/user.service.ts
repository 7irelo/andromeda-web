import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { AuthService } from './auth.service';
import { User } from './user.model';
import { Post } from './post.model'; // Adjust as per your models

@Injectable({
  providedIn: 'root'
})
export class UserService {
  private apiUrl = 'http://localhost:8000/api';

  constructor(
    private http: HttpClient,
    private authService: AuthService
  ) { }

  getUserProfile(username: string): Observable<User> {
    const url = `${this.apiUrl}/users/${username}/`;
    return this.http.get<User>(url, { withCredentials: true }).pipe(
      catchError(error => {
        return throwError('Error fetching user profile');
      })
    );
  }

  updateUserProfile(username: string, userData: any): Observable<User> {
    const url = `${this.apiUrl}/users/${username}/`;
    return this.http.put<User>(url, userData, { withCredentials: true }).pipe(
      catchError(error => {
        return throwError('Error updating user profile');
      })
    );
  }

  getFriends(username: string): Observable<User[]> {
    const url = `${this.apiUrl}/users/${username}/friends/`;
    return this.http.get<User[]>(url, { withCredentials: true }).pipe(
      catchError(error => {
        return throwError('Error fetching friends');
      })
    );
  }

  addFriend(username: string): Observable<any> {
    const url = `${this.apiUrl}/users/${username}/friends/`;
    return this.http.post<any>(url, {}, { withCredentials: true }).pipe(
      catchError(error => {
        return throwError('Error adding friend');
      })
    );
  }

  removeFriend(username: string): Observable<any> {
    const url = `${this.apiUrl}/users/${username}/friends/`;
    return this.http.delete<any>(url, { withCredentials: true }).pipe(
      catchError(error => {
        return throwError('Error removing friend');
      })
    );
  }

  getUserPosts(username: string): Observable<Post[]> {
    const url = `${this.apiUrl}/users/${username}/posts/`;
    return this.http.get<Post[]>(url, { withCredentials: true }).pipe(
      catchError(error => {
        return throwError('Error fetching user posts');
      })
    );
  }

  // Add more methods as needed for user-related operations
}
