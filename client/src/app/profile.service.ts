import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { AuthService } from './auth.service'; // Assuming AuthService manages authentication

@Injectable({
  providedIn: 'root'
})
export class ProfileService {
  private apiUrl = 'http://localhost:8000/users/';

  constructor(
    private http: HttpClient,
    private authService: AuthService // Inject AuthService
  ) { }

  getUserProfile(): Observable<any> {
    // Assuming you have a method in AuthService to get the authenticated user's ID or username
    const userId = this.authService.getAuthenticatedUserId(); // Adjust this based on your AuthService implementation
    const url = `${this.apiUrl}${userId}/`; // Construct URL based on the authenticated user's ID or username
    return this.http.get<any>(url, { withCredentials: true });
  }
}
