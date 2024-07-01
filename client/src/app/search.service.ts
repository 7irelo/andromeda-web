import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class SearchService {
  private querySubject = new BehaviorSubject<string>('');
  currentQuery = this.querySubject.asObservable();

  constructor() {}

  changeQuery(query: string) {
    this.querySubject.next(query);
  }
}
