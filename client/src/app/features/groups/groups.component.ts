import { Component, OnInit, ChangeDetectionStrategy } from '@angular/core';
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
import { EmptyStateComponent, ErrorStateComponent, SkeletonComponent } from '../../shared/components/states';
import { ModalDialogDirective } from '../../shared/a11y/modal-dialog.directive';

@Component({
    selector: 'app-groups',
    imports: [
        CommonModule, RouterLink, ReactiveFormsModule,
        MatIconModule, MatButtonModule, MatTabsModule, MatProgressSpinnerModule,
        MatFormFieldModule, MatInputModule, MatSelectModule, MatSnackBarModule,
        EmptyStateComponent, ErrorStateComponent, SkeletonComponent, ModalDialogDirective,
    ],
    templateUrl: './groups.component.html',
    changeDetection: ChangeDetectionStrategy.Eager,
    styleUrls: ['./groups.component.scss']
})
export class GroupsComponent implements OnInit {
  allGroups: Group[] = [];
  myGroups: Group[] = [];
  loading = false;
  loadError = false;
  mineLoading = false;
  mineError = false;

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
    this.loadError = false;
    this.apiService.getGroups().subscribe({
      next: (res) => {
        this.allGroups = res.results;
        this.loading = false;
      },
      error: () => {
        this.loading = false;
        this.loadError = true;
      },
    });
  }

  loadMine(): void {
    this.mineLoading = true;
    this.mineError = false;
    this.apiService.getGroups({ mine: 'true' }).subscribe({
      next: (res) => {
        this.myGroups = res.results;
        this.mineLoading = false;
      },
      error: () => {
        this.mineLoading = false;
        this.mineError = true;
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
