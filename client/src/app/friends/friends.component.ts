import { Component, OnInit } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { UserService } from '../user.service';
import { User } from '../user.model'; // Assuming you have a User model defined

@Component({
  selector: 'app-friends',
  templateUrl: './friends.component.html',
  styleUrls: ['./friends.component.css']
})
export class FriendsComponent implements OnInit {
  username: string;
  friends: User[] = []; // Adjust according to your User model
  errorMessage: string = '';

  constructor(private route: ActivatedRoute, private userService: UserService) { }

  ngOnInit(): void {
    this.route.params.subscribe(params => {
      this.username = params['username'];
      this.loadUserFriends();
    });
  }

  loadUserFriends(): void {
    this.userService.getUserFriends(this.username).subscribe(
      data => {
        this.friends = data;
      },
      error => {
        console.error('Error fetching user friends', error);
        this.errorMessage = 'Error fetching user friends';
      }
    );
  }
}
