import { Component, Input, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../../environments/environment';

interface Group {
  id: number;
  name: string;
  cover_photo: string;
  description: string;
  members_count: number;
  privacy: string;
  is_member: boolean;
}

@Component({
  selector: 'app-group-detail',
  standalone: true,
  imports: [CommonModule, MatButtonModule, MatIconModule, MatProgressSpinnerModule],
  template: `
    <div class="group-detail" *ngIf="group">
      <div class="group-cover">
        <img [src]="group.cover_photo || 'assets/default-cover.png'" alt="" />
      </div>
      <div class="group-body">
        <h1>{{ group.name }}</h1>
        <p class="text-secondary">{{ group.members_count }} members · {{ group.privacy }}</p>
        <p *ngIf="group.description">{{ group.description }}</p>
        <div class="group-actions">
          <button mat-flat-button color="primary" *ngIf="!group.is_member" (click)="join()">Join Group</button>
          <button mat-stroked-button color="warn" *ngIf="group.is_member" (click)="leave()">Leave Group</button>
        </div>
      </div>
    </div>
    <mat-spinner *ngIf="loading" diameter="40" style="margin:40px auto;display:block"></mat-spinner>
  `,
  styles: [`.group-detail{max-width:800px;margin:0 auto;padding:16px} .group-cover{height:200px;border-radius:8px;overflow:hidden;margin-bottom:16px} .group-cover img{width:100%;height:100%;object-fit:cover} .group-body{padding:0 8px;display:flex;flex-direction:column;gap:8px} .group-actions{margin-top:8px}`]
})
export class GroupDetailComponent implements OnInit {
  @Input() id!: string;
  group: Group | null = null;
  loading = false;

  constructor(private http: HttpClient) {}

  ngOnInit(): void {
    this.loading = true;
    this.http.get<Group>(`${environment.apiUrl}/groups/${this.id}/`).subscribe({
      next: (g) => { this.group = g; this.loading = false; },
      error: () => (this.loading = false),
    });
  }

  join(): void {
    this.http.post(`${environment.apiUrl}/groups/${this.group!.id}/join/`, {}).subscribe(() => {
      this.group!.is_member = true;
    });
  }

  leave(): void {
    this.http.post(`${environment.apiUrl}/groups/${this.group!.id}/leave/`, {}).subscribe(() => {
      this.group!.is_member = false;
    });
  }
}
