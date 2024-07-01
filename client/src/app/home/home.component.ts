import { Component, OnInit } from '@angular/core';
import { FormBuilder, FormGroup } from '@angular/forms';
import { PostService } from '../post.service';

@Component({
  selector: 'app-home',
  templateUrl: './home.component.html',
  styleUrls: ['./home.component.css']
})
export class HomeComponent implements OnInit {
  posts: any[] = [];
  message: string = '';
  searchForm: FormGroup;

  constructor(
    private formBuilder: FormBuilder,
    private postService: PostService
  ) {
    this.searchForm = this.formBuilder.group({
      query: ['']
    });
  }

  ngOnInit(): void {
    this.loadPosts();
  }

  loadPosts(query: string = ''): void {
    this.postService.getPosts(query).subscribe(
      data => {
        this.posts = data;
        this.message = this.posts.length ? '' : 'No posts found';
      },
      error => {
        console.error('Error fetching posts', error);
        this.message = 'Error fetching posts';
      }
    );
  }

  onSearch(): void {
    const query = this.searchForm.get('query')?.value || '';
    this.loadPosts(query);
  }
}
