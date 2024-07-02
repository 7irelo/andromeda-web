import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, forkJoin, throwError } from 'rxjs';
import { catchError, map } from 'rxjs/operators';
import { Post } from './post.model';

@Injectable({
  providedIn: 'root'
})
export class PostService {
  private baseUrl = 'http://localhost:8000/api';

  constructor(private http: HttpClient) { }

  getRecommendedPosts(): Observable<Post[]> {
    return this.http.get<any[]>(`${this.baseUrl}/posts/recommended/`).pipe(
      map(data => data.map(item => new Post(item))),
      catchError(error => {
        console.error('Error fetching recommended posts', error);
        return throwError('Error fetching recommended posts');
      })
    );
  }

  getPosts(query: string = ''): Observable<Post[]> {
    return this.http.get<any[]>(`${this.baseUrl}/posts?q=${query}`).pipe(
      map(data => data.map(item => new Post(item))),
      catchError(error => {
        console.error('Error fetching posts', error);
        return throwError('Error fetching posts');
      })
    );
  }

  getPostById(id: number): Observable<Post> {
    return this.http.get<any>(`${this.baseUrl}/posts/${id}/`).pipe(
      map(data => new Post(data)),
      catchError(error => {
        console.error('Error fetching post by ID', error);
        return throwError('Error fetching post by ID');
      })
    );
  }

  getCommentsByPostId(postId: number): Observable<any[]> {
    return this.http.get<any[]>(`${this.baseUrl}/posts/${postId}/comments/`).pipe(
      catchError(error => {
        console.error('Error fetching comments by post ID', error);
        return throwError('Error fetching comments by post ID');
      })
    );
  }

  getCommentById(postId: number, commentId: number): Observable<any> {
    return this.http.get<any>(`${this.baseUrl}/posts/${postId}/comments/${commentId}/`).pipe(
      catchError(error => {
        console.error('Error fetching comment by ID', error);
        return throwError('Error fetching comment by ID');
      })
    );
  }

  getDataFromMultipleUrls(urls: string[]): Observable<any[]> {
    const requests = urls.map(url => this.http.get(url));
    return forkJoin(requests).pipe(
      catchError(error => {
        console.error('Error fetching data from multiple URLs', error);
        return throwError('Error fetching data from multiple URLs');
      })
    );
  }
}
