import { Component, OnInit } from '@angular/core';
import { FormBuilder, FormGroup } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { Emitters } from '../emitters/emitters';
import { PostService } from '../post.service';

@Component({
  selector: 'app-home',
  templateUrl: './home.component.html',
  styleUrls: ['./home.component.css']
})
export class HomeComponent implements OnInit {
  posts: any[] = [];
  message: string = '';
  form: FormGroup;

  constructor(
    private formBuilder: FormBuilder,
    private http: HttpClient,
    private router: Router,
    private postService: PostService
  ) {
    this.form = this.formBuilder.group({
      // Add your form controls here
      // Example: name: ['']
    });
  }

  ngOnInit(): void {
    this.postService.getPosts().subscribe(
      data => {
        this.posts = data;
      },
      error => {
        console.error('Error fetching posts', error);
      }
    );
  }
  
  submit(): void {
    this.http.post('http://localhost:8000/api/register', this.form.getRawValue())
      .subscribe(() => this.router.navigate(['/login']));
  }
}
