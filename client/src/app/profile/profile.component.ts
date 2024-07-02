import { Component, OnInit } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { UserService } from '../user.service';
import { Post } from '../post.model'; // Assuming you have a Post model defined

@Component({
  selector: 'app-profile',
  templateUrl: './profile.component.html',
  styleUrls: ['./profile.component.css']
})
export class ProfileComponent implements OnInit {
  username: string;
  posts: Post[] = []; // Adjust according to your Post model
  errorMessage: string = '';

  constructor(private route: ActivatedRoute, private userService: UserService) { }

  ngOnInit(): void {
    this.route.params.subscribe(params => {
      this.username = params['username'];
      this.loadUserPosts();
    });
  }

  loadUserPosts(): void {
    this.userService.getUserPosts(this.username).subscribe(
      data => {
        this.posts = data;
      },
      error => {
        console.error('Error fetching user posts', error);
        this.errorMessage = 'Error fetching user posts';
      }
    );
  }
}
