import { Component, OnInit } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { CommonModule } from '@angular/common';
import { NavbarComponent } from './shared/components/navbar/navbar.component';
import { AuthService } from './core/services/auth.service';
import { WebSocketService } from './core/services/websocket.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, CommonModule, NavbarComponent],
  template: `
    <app-navbar *ngIf="authService.isLoggedIn()"></app-navbar>
    <main [class.with-nav]="authService.isLoggedIn()">
      <router-outlet></router-outlet>
    </main>
  `,
  styles: [`
    main { min-height: 100vh; }
    main.with-nav { padding-top: 56px; }
  `],
})
export class AppComponent implements OnInit {
  constructor(
    public authService: AuthService,
    private wsService: WebSocketService,
  ) {}

  ngOnInit(): void {
    if (this.authService.isLoggedIn()) {
      this.wsService.connectNotifications();
    }
    this.authService.currentUser$.subscribe((user) => {
      if (user) this.wsService.connectNotifications();
      else this.wsService.disconnect();
    });
  }
}
