import { HttpClient } from '@angular/common/http';
import { Component, OnInit } from '@angular/core';
import { FormBuilder, FormGroup } from '@angular/forms';
import { Emitters } from '../emitters/emitters';
import { SearchService } from '../search.service';

@Component({
  selector: 'app-nav',
  templateUrl: './nav.component.html',
  styleUrls: ['./nav.component.css']
})
export class NavComponent implements OnInit {
  authenticated = false;
  searchForm: FormGroup;

  constructor(
    private http: HttpClient,
    private formBuilder: FormBuilder,
    private searchService: SearchService
  ) {
    this.searchForm = this.formBuilder.group({
      query: ['']
    });
  }

  ngOnInit(): void {
    Emitters.authEmitter.subscribe(
      (auth: boolean) => {
        this.authenticated = auth;
      }
    );
  }
  
  logout(): void {
    this.http.post('http://localhost:8000/api/logout', {}, { withCredentials: true })
      .subscribe(() => this.authenticated = false);
  }

  onSearch(): void {
    const query = this.searchForm.get('query')?.value || '';
    this.searchService.changeQuery(query);
  }
}
