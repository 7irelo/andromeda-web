import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../environments/environment'; // Adjust as per your environment setup
import { User } from './user.model';

@Injectable({
  providedIn: 'root'
})
export class UserService {
  private baseUrl = environment.apiUrl; // Adjust to your backend API URL

  constructor(private http: HttpClient) { }

  getUser(username: string): Observable<User> {
    return this.http.get<User>(`${this.baseUrl}/users/${username}/`);
  }

  updateUser(username: string, userData: any): Observable<User> {
    return this.http.put<User>(`${this.baseUrl}/users/${username}/`, userData);
  }

  // Add more methods as needed (e.g., fetching user posts, friends, etc.)
}
