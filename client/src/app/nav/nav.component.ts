import { HttpClient } from '@angular/common/http';
import { Component, OnInit } from '@angular/core';
import { Emitters } from '../emitters/emitters';

@Component({
  selector: 'app-nav',
  templateUrl: './nav.component.html',
  styleUrl: './nav.component.css'
})
export class NavComponent implements OnInit {
  authenticated = false;
  constructor(private http: HttpClient) {}

  ngOnInit(): void {
      Emitters.authEmmitter.subscribe(
          (auth: boolean) => {
              this.authenticated = auth;
          }
      );
  }
  
  logout() : void {
      this.http.post('http://localhost:5000/api/logout', {}, { withCredsntials: true })
      .subscribe(() => this.authenticated = false);
  }

}
