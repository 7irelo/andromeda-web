import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { ApiService } from '../../../core/services/api.service';
import { Post } from '../../../models/post.model';
import { User } from '../../../models/user.model';
import { ImageCropperComponent, ImageCropperResult } from '../image-cropper/image-cropper.component';

@Component({
  selector: 'app-create-post',
  standalone: true,
  imports: [CommonModule, FormsModule, MatIconModule, MatButtonModule, MatProgressSpinnerModule, MatDialogModule],
  template: `
    <div class="create-post card">
      <div class="create-top">
        <img [src]="currentUser?.avatar_url || 'assets/default-avatar.png'" class="avatar md" alt="You" />
        <div class="textarea-wrapper" [class.expanded]="expanded">
          <textarea
            [(ngModel)]="content"
            [placeholder]="placeholder"
            (focus)="expanded = true"
            rows="1"
            class="post-textarea"
          ></textarea>
        </div>
      </div>

      <div class="image-preview-wrap" *ngIf="imagePreview">
        <img [src]="imagePreview" class="preview-img" alt="Preview" />
        <button class="remove-preview" (click)="removeImage()" type="button">
          <mat-icon>close</mat-icon>
        </button>
      </div>

      <div class="create-actions" *ngIf="expanded">
        <div class="media-btns">
          <button mat-button class="media-btn" (click)="imageInput.click()">
            <mat-icon style="color:#45bd62">photo_camera</mat-icon> Photo/Video
          </button>
          <button mat-button class="media-btn">
            <mat-icon style="color:#f7b928">emoji_emotions</mat-icon> Feeling/Activity
          </button>
        </div>
        <button
          mat-flat-button color="primary"
          class="post-btn"
          (click)="submit()"
          [disabled]="(!content.trim() && !selectedFile) || loading"
        >
          <mat-spinner diameter="16" *ngIf="loading"></mat-spinner>
          <span *ngIf="!loading">Post</span>
        </button>
      </div>

      <input #imageInput type="file" accept="image/*,video/*" hidden (change)="onFileSelected($event)" />
    </div>
  `,
  styles: [`
    .create-post { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
    .create-top { display: flex; align-items: flex-start; gap: 10px; }
    .textarea-wrapper { flex: 1; }
    .post-textarea {
      width: 100%;
      border: none;
      background: var(--bg);
      border-radius: 20px;
      padding: 10px 16px;
      font-size: 15px;
      resize: none;
      outline: none;
      font-family: inherit;
      color: var(--text-primary);
      min-height: 42px;
      &::placeholder { color: var(--text-secondary); }
    }
    .textarea-wrapper.expanded .post-textarea { border-radius: 8px; min-height: 80px; }
    .image-preview-wrap {
      position: relative;
      border-radius: 8px;
      overflow: hidden;
      border: 1px solid var(--border);
    }
    .preview-img { width: 100%; max-height: 240px; object-fit: cover; display: block; }
    .remove-preview {
      position: absolute;
      top: 8px;
      right: 8px;
      background: rgba(0,0,0,.6);
      color: #fff;
      border: none;
      border-radius: 50%;
      width: 28px;
      height: 28px;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      mat-icon { font-size: 16px; width: 16px; height: 16px; }
    }
    .create-actions { display: flex; justify-content: space-between; align-items: center; border-top: 1px solid var(--border); padding-top: 12px; }
    .media-btns { display: flex; gap: 4px; }
    .media-btn { border-radius: 8px; }
    .post-btn { min-width: 80px; display: flex; align-items: center; gap: 6px; }
  `],
})
export class CreatePostComponent {
  @Input() currentUser: User | null = null;
  @Output() postCreated = new EventEmitter<Post>();

  content = '';
  expanded = false;
  loading = false;
  selectedFile: File | null = null;
  imagePreview: string | null = null;

  get placeholder(): string {
    return `What's on your mind, ${this.currentUser?.first_name || 'you'}?`;
  }

  constructor(private apiService: ApiService, private dialog: MatDialog) {}

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    if (!file) return;
    // For image files, open the cropper; for video just attach directly
    if (file.type.startsWith('image/')) {
      const ref = this.dialog.open(ImageCropperComponent, {
        data: { file, aspectRatio: 0, title: 'Crop Image' },
        width: '550px',
      });
      ref.afterClosed().subscribe((result: ImageCropperResult | undefined) => {
        if (result) {
          this.selectedFile = new File([result.blob], file.name, { type: 'image/jpeg' });
          this.imagePreview = result.dataUrl;
          this.expanded = true;
        }
      });
    } else {
      this.selectedFile = file;
      const reader = new FileReader();
      reader.onload = (e) => { this.imagePreview = e.target?.result as string; };
      reader.readAsDataURL(file);
      this.expanded = true;
    }
    // Reset input so the same file can be re-selected
    input.value = '';
  }

  removeImage(): void {
    this.selectedFile = null;
    this.imagePreview = null;
  }

  submit(): void {
    if (!this.content.trim() && !this.selectedFile) return;
    this.loading = true;

    const data = new FormData();
    data.append('content', this.content);
    data.append('post_type', this.selectedFile ? 'image' : 'text');
    if (this.selectedFile) data.append('image', this.selectedFile);

    this.apiService.createPost(data).subscribe({
      next: (post) => {
        this.postCreated.emit(post);
        this.content = '';
        this.selectedFile = null;
        this.imagePreview = null;
        this.expanded = false;
        this.loading = false;
      },
      error: () => (this.loading = false),
    });
  }
}
