import { Component, OnInit } from '@angular/core';
import { FormBuilder, FormGroup } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { Emitters } from '../emitters/emitters';

@Component({
  selector: 'app-home',
  templateUrl: './home.component.html',
  styleUrl: './home.component.css'
})
export class HomeComponent implements OnInit {
  message = ''
  constructor(
      private formBuilder: FormBuilder,
      private http: HttpClient,
      private router: Router
      ) {}

  ngOnInit(): void {
      this.http.get('http://localhost:8000/api', { withCredentials:true }).subscribe(
          (res: any) => {
              this.message = `Hello ${res.user}`
              Emitters.authEmmitter.emit(true);
          }
          err => {
              this.message = "You are not logged in"
              Emitters.authEmmitter.emit(false);
          }
          );
      this.form = this.formBuilder.group({
          name: '',
          surname: '',
          email: '',
          password: ''
      });
  }
  
  submit(): void {
      this.http.post('http://localhost:5000/api/register', this.form.getRawValue())
      .subscribe(() => this.router.navigate(['/login']));
  }
}

