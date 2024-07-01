import { Component, OnInit } from '@angular/core';
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

  constructor(
    private postService: PostService,
    private searchService: SearchService
  ) {}

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
}
