import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class PostService {
  private baseUrl = 'http://localhost:8000/api';

  constructor(private http: HttpClient) { }

  getPosts(query: string = ''): Observable<any[]> {
    return this.http.get<any[]>(`${this.baseUrl}/posts?q=${query}`);
  }

  getPostById(id: number): Observable<any> {
    return this.http.get<any>(`${this.baseUrl}/posts/${id}/`);
  }

  getCommentsByPostId(postId: number): Observable<any[]> {
    return this.http.get<any[]>(`${this.baseUrl}/posts/${postId}/comments/`);
  }

  getCommentById(postId: number, commentId: number): Observable<any> {
    return this.http.get<any>(`${this.baseUrl}/posts/${postId}/comments/${commentId}/`);
  }

  getDataFromMultipleUrls(urls: string[]): Observable<any[]> {
    const requests = urls.map(url => this.http.get(url));
    return forkJoin(requests);
  }
}
