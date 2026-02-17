import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatTabsModule } from '@angular/material/tabs';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../core/services/api.service';

@Component({
  selector: 'app-groups',
  standalone: true,
  imports: [CommonModule, RouterLink, MatIconModule, MatButtonModule, MatTabsModule, MatProgressSpinnerModule],
  templateUrl: './groups.component.html',
  styleUrls: ['./groups.component.scss'],
})
export class GroupsComponent implements OnInit {
  allGroups: unknown[] = [];
  myGroups: unknown[] = [];
  loading = false;

  constructor(private apiService: ApiService) {}

  ngOnInit(): void {
    this.loadAll();
    this.loadMine();
  }

  loadAll(): void {
    this.loading = true;
    this.apiService.getGroups().subscribe({
      next: (res: unknown) => {
        this.allGroups = (res as { results: unknown[] }).results;
        this.loading = false;
      },
      error: () => (this.loading = false),
    });
  }

  loadMine(): void {
    this.apiService.getGroups({ mine: 'true' }).subscribe({
      next: (res: unknown) => {
        this.myGroups = (res as { results: unknown[] }).results;
      },
    });
  }

  join(group: unknown): void {
    const g = group as { id: number };
    this.apiService.joinGroup(g.id).subscribe(() => this.loadAll());
  }

  asGroup(g: unknown): { id: number; name: string; cover_photo: string | null; members_count: number; privacy: string; is_member: boolean } {
    return g as { id: number; name: string; cover_photo: string | null; members_count: number; privacy: string; is_member: boolean };
  }
}
