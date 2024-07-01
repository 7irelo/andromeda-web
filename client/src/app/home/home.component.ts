import { Component, OnInit } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { PostService } from '../post.service';
import { SearchService } from '../search.service';

@Component({
  selector: 'app-home',
  templateUrl: './home.component.html',
  styleUrls: ['./home.component.css']
})
export class HomeComponent implements OnInit {
  posts: any[] = [];
  message: string = '';
  showPostForm: boolean = false;
  postText: string = '';
  postForm: FormGroup;

  constructor(
    private postService: PostService,
    private searchService: SearchService,
    private formBuilder: FormBuilder
  ) {
    this.postForm = this.formBuilder.group({
      text: ['', Validators.required]
    });
  }

  ngOnInit(): void {
    this.searchService.currentQuery.subscribe(query => {
      this.loadPosts(query);
    });
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

  togglePostForm(): void {
    this.showPostForm = !this.showPostForm;
  }

  submitPost(): void {
    if (this.postForm.valid) {
      const postData = {
        text: this.postForm.value.text
      };

      this.postService.createPost(postData).subscribe(
        data => {
          // Refresh posts after successful creation
          this.loadPosts();
          this.showPostForm = false; // Hide the form after successful submission
          this.postForm.reset(); // Reset the form
        },
        error => {
          console.error('Error creating post', error);
          // Handle error if needed
        }
      );
    }
  }
}
