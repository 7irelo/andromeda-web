import { Component, OnInit } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { PostService } from '../post.service';
import { SearchService } from '../search.service';
import { LogoutService } from '../logout.service';

@Component({
  selector: 'app-home',
  templateUrl: './home.component.html',
  styleUrls: ['./home.component.css']
})
export class HomeComponent implements OnInit {
  posts: any[] = [];
  recommendedPosts: any[] = []; // Added recommendedPosts array
  message: string = '';
  showPostForm: boolean = false;
  postText: string = '';
  postForm: FormGroup;
  showLogoutPopup: boolean = false;

  constructor(
    private postService: PostService,
    private searchService: SearchService,
    private formBuilder: FormBuilder,
    private logoutService: LogoutService
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
    this.loadRecommendedPosts(); // Load recommended posts on component initialization
    this.logoutService.showLogoutPopup.subscribe(show => {
      this.showLogoutPopup = show;
    });
  }

  loadRecommendedPosts(): void {
    this.postService.getRecommendedPosts().subscribe(
      data => {
        this.recommendedPosts = data;
      },
      error => {
        console.error('Error fetching recommended posts', error);
      }
    );
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
          this.loadPosts();
          this.showPostForm = false;
          this.postForm.reset();
        },
        error => {
          console.error('Error creating post', error);
        }
      );
    }
  }

  confirmLogout(): void {
    this.logoutService.logout();
    this.showLogoutPopup = false;
  }

  cancelLogout(): void {
    this.showLogoutPopup = false;
  }
}
