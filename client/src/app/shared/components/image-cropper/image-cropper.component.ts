import {
  Component, AfterViewInit, OnDestroy,
  ViewChild, ElementRef, Inject,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import Cropper from 'cropperjs';

export interface ImageCropperData {
  file: File;
  aspectRatio?: number; // 1 = square, 16/9 = cover, NaN/0 = free
  title?: string;
}

export interface ImageCropperResult {
  blob: Blob;
  dataUrl: string;
}

@Component({
  selector: 'app-image-cropper',
  standalone: true,
  imports: [CommonModule, MatButtonModule, MatIconModule, MatDialogModule],
  template: `
    <h2 mat-dialog-title>{{ data.title || 'Crop Image' }}</h2>
    <mat-dialog-content class="cropper-content">
      <div class="cropper-wrapper">
        <img #cropperImage [src]="imageSrc" alt="Crop" />
      </div>
      <div class="cropper-controls">
        <button mat-icon-button (click)="rotate(-90)" title="Rotate left">
          <mat-icon>rotate_left</mat-icon>
        </button>
        <button mat-icon-button (click)="rotate(90)" title="Rotate right">
          <mat-icon>rotate_right</mat-icon>
        </button>
        <button mat-icon-button (click)="zoom(0.1)" title="Zoom in">
          <mat-icon>zoom_in</mat-icon>
        </button>
        <button mat-icon-button (click)="zoom(-0.1)" title="Zoom out">
          <mat-icon>zoom_out</mat-icon>
        </button>
        <button mat-icon-button (click)="reset()" title="Reset">
          <mat-icon>restart_alt</mat-icon>
        </button>
      </div>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-stroked-button mat-dialog-close>Cancel</button>
      <button mat-flat-button color="primary" (click)="crop()">
        <mat-icon>check</mat-icon> Save
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    .cropper-content { padding: 0; overflow: hidden; }
    .cropper-wrapper {
      width: 100%;
      max-height: 400px;
      overflow: hidden;
      img { display: block; max-width: 100%; }
    }
    .cropper-controls {
      display: flex;
      justify-content: center;
      gap: 8px;
      padding: 12px 0 4px;
    }
    mat-dialog-actions { padding: 12px 24px; }
  `]
})
export class ImageCropperComponent implements AfterViewInit, OnDestroy {
  @ViewChild('cropperImage') imageEl!: ElementRef<HTMLImageElement>;

  imageSrc = '';
  private cropper!: Cropper;

  constructor(
    private dialogRef: MatDialogRef<ImageCropperComponent>,
    @Inject(MAT_DIALOG_DATA) public data: ImageCropperData,
  ) {
    const reader = new FileReader();
    reader.onload = () => (this.imageSrc = reader.result as string);
    reader.readAsDataURL(data.file);
  }

  ngAfterViewInit(): void {
    // Small timeout to let image src bind
    setTimeout(() => this.initCropper(), 100);
  }

  ngOnDestroy(): void {
    this.cropper?.destroy();
  }

  private initCropper(): void {
    const ratio = this.data.aspectRatio;
    this.cropper = new Cropper(this.imageEl.nativeElement, {
      aspectRatio: ratio && ratio > 0 ? ratio : NaN,
      viewMode: 1,
      dragMode: 'move',
      autoCropArea: 0.9,
      responsive: true,
      background: false,
    });
  }

  rotate(deg: number): void { this.cropper?.rotate(deg); }
  zoom(ratio: number): void { this.cropper?.zoom(ratio); }
  reset(): void { this.cropper?.reset(); }

  crop(): void {
    const canvas = this.cropper.getCroppedCanvas({
      maxWidth: 2048,
      maxHeight: 2048,
      imageSmoothingEnabled: true,
      imageSmoothingQuality: 'high',
    });
    canvas.toBlob((blob) => {
      if (blob) {
        const result: ImageCropperResult = {
          blob,
          dataUrl: canvas.toDataURL('image/jpeg', 0.92),
        };
        this.dialogRef.close(result);
      }
    }, 'image/jpeg', 0.92);
  }
}
