import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatTabsModule } from '@angular/material/tabs';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../core/services/api.service';
import { Group } from '../../models/group.model';

@Component({
  selector: 'app-groups',
  standalone: true,
  imports: [
    CommonModule, RouterLink, ReactiveFormsModule,
    MatIconModule, MatButtonModule, MatTabsModule, MatProgressSpinnerModule,
    MatFormFieldModule, MatInputModule, MatSelectModule, MatSnackBarModule,
  ],
  templateUrl: './groups.component.html',
  styleUrls: ['./groups.component.scss'],
})
export class GroupsComponent implements OnInit {
  allGroups: Group[] = [];
  myGroups: Group[] = [];
  loading = false;

  isCreating = false;
  saving = false;
  createForm!: FormGroup;

  readonly privacyOptions = [
    { value: 'public', label: 'Public' },
    { value: 'private', label: 'Private' },
    { value: 'secret', label: 'Secret' },
  ];

  constructor(
    private apiService: ApiService,
    private fb: FormBuilder,
    private snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.loadAll();
    this.loadMine();
  }

  loadAll(): void {
    this.loading = true;
    this.apiService.getGroups().subscribe({
      next: (res) => {
        this.allGroups = res.results;
        this.loading = false;
      },
      error: () => (this.loading = false),
    });
  }

  loadMine(): void {
    this.apiService.getGroups({ mine: 'true' }).subscribe({
      next: (res) => {
        this.myGroups = res.results;
      },
    });
  }

  join(group: Group): void {
    this.apiService.joinGroup(group.id).subscribe(() => this.loadAll());
  }

  openCreateDialog(): void {
    this.createForm = this.fb.group({
      name: ['', Validators.required],
      description: [''],
      privacy: ['public', Validators.required],
    });
    this.isCreating = true;
  }

  saveCreate(): void {
    if (this.createForm.invalid || this.saving) return;
    this.saving = true;
    this.apiService.createGroup(this.createForm.value).subscribe({
      next: () => {
        this.isCreating = false;
        this.saving = false;
        this.snackBar.open('Group created!', 'Dismiss', { duration: 3000 });
        this.loadAll();
        this.loadMine();
      },
      error: () => {
        this.saving = false;
        this.snackBar.open('Failed to create group', 'Dismiss', { duration: 3000 });
      },
    });
  }

  cancelCreate(): void {
    this.isCreating = false;
  }
}
