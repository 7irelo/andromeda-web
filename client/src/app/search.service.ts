import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class SearchService {
  private querySubject: BehaviorSubject<string> = new BehaviorSubject<string>('');
  currentQuery: Observable<string> = this.querySubject.asObservable();

  constructor() {}

  /**
   * Updates the current search query.
   * @param query - The new search query string.
   */
  updateQuery(query: string): void {
    this.querySubject.next(query);
  }
}
