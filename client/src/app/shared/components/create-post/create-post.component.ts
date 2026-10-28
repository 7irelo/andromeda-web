import { Component, ElementRef, Input, OnDestroy, OnInit, Output, EventEmitter, ViewChild, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { HttpErrorResponse } from '@angular/common/http';
import { Subject, Subscription, debounceTime, distinctUntilChanged, of, switchMap, catchError, map } from 'rxjs';
import { ApiService } from '../../../core/services/api.service';
import { Post } from '../../../models/post.model';
import { User } from '../../../models/user.model';
import { ImageCropperComponent, ImageCropperResult } from '../image-cropper/image-cropper.component';
import { ComposeAssistComponent } from '../compose-assist/compose-assist.component';

const MAX_IMAGES = 10;
// The "@partial" right before the caret. Mirrors the server's mention syntax.
const MENTION_AT_CARET = /(?:^|[^\p{L}\p{N}_@])@([\p{L}\p{N}_.+-]{2,30})$/u;

/** First message in a DRF error body, however deeply nested (e.g. `{images: {1: ['Not an image']}}`). */
function firstError(body: unknown, depth = 0): string {
  if (typeof body === 'string') return body;
  if (!body || typeof body !== 'object' || depth > 3) return '';
  for (const value of Object.values(body as Record<string, unknown>)) {
    const msg = firstError(value, depth + 1);
    if (msg) return msg;
  }
  return '';
}

interface DraftImage {
  file: File;
  url: string;
}

@Component({
    selector: 'app-create-post',
    imports: [CommonModule, FormsModule, MatIconModule, MatButtonModule, MatProgressSpinnerModule, MatDialogModule,
        ComposeAssistComponent],
    template: `
    <div class="create-post card">
      <div class="create-top">
        <img [src]="currentUser?.avatar_url || 'assets/default-avatar.png'" class="avatar md" alt="" />
        <div class="textarea-wrapper" [class.expanded]="expanded">
          <textarea
            #textarea
            [(ngModel)]="content"
            [placeholder]="placeholder"
            aria-label="Write a post"
            (focus)="expanded = true"
            (input)="onTextInput()"
            (click)="onTextInput()"
            (keydown)="onTextKeydown($event)"
            (blur)="closeMentionsSoon()"
            rows="1"
            maxlength="10000"
            class="post-textarea"
            role="combobox"
            aria-autocomplete="list"
            [attr.aria-expanded]="mentionResults.length > 0"
            aria-controls="mention-list"
            [attr.aria-activedescendant]="mentionResults.length ? 'mention-' + mentionIndex : null"
          ></textarea>
          <ul id="mention-list" class="mention-list" role="listbox" *ngIf="mentionResults.length" aria-label="People to mention">
            <li *ngFor="let u of mentionResults; let i = index" role="option" [id]="'mention-' + i"
                [attr.aria-selected]="i === mentionIndex" [class.active]="i === mentionIndex"
                (mousedown)="$event.preventDefault(); insertMention(u)">
              <img [src]="u.avatar_url || 'assets/default-avatar.png'" class="avatar xs" alt="" />
              <span class="m-name">{{ u.full_name }}</span>
              <span class="m-user">&#64;{{ u.username }}</span>
            </li>
          </ul>
        </div>
      </div>

      <!-- Images, in the order they'll be shown. Drag to reorder, or use the arrow buttons. -->
      <ul class="draft-images" *ngIf="images.length" aria-label="Selected images, in display order">
        <li *ngFor="let img of images; let i = index; let last = last"
            draggable="true" (dragstart)="dragFrom = i" (dragover)="$event.preventDefault()" (drop)="dropOn(i)"
            [class.dragging]="dragFrom === i">
          <img [src]="img.url" [alt]="'Image ' + (i + 1) + ' of ' + images.length" />
          <span class="order-badge" aria-hidden="true">{{ i + 1 }}</span>
          <div class="thumb-actions">
            <button type="button" (click)="move(i, -1)" [disabled]="i === 0" [attr.aria-label]="'Move image ' + (i + 1) + ' earlier'">
              <mat-icon>chevron_left</mat-icon>
            </button>
            <button type="button" (click)="crop(i)" [attr.aria-label]="'Crop image ' + (i + 1)">
              <mat-icon>crop</mat-icon>
            </button>
            <button type="button" (click)="removeImageAt(i)" [attr.aria-label]="'Remove image ' + (i + 1)">
              <mat-icon>close</mat-icon>
            </button>
            <button type="button" (click)="move(i, 1)" [disabled]="last" [attr.aria-label]="'Move image ' + (i + 1) + ' later'">
              <mat-icon>chevron_right</mat-icon>
            </button>
          </div>
        </li>
      </ul>
      <p class="sr-only" aria-live="polite">{{ liveMessage }}</p>

      <div class="image-preview-wrap" *ngIf="videoFile">
        <video [src]="videoUrl" class="preview-img" controls muted></video>
        <button class="remove-preview" (click)="removeVideo()" type="button" aria-label="Remove video">
          <mat-icon>close</mat-icon>
        </button>
      </div>

      <p class="error" *ngIf="error" role="alert">{{ error }}</p>

      <app-compose-assist *ngIf="expanded" [text]="content" kind="post" (accepted)="content = $event"></app-compose-assist>

      <div class="create-actions" *ngIf="expanded">
        <div class="media-btns">
          <button mat-button class="media-btn" (click)="imageInput.click()" [disabled]="images.length >= maxImages || !!videoFile">
            <mat-icon style="color:#45bd62">photo_library</mat-icon> Photos
          </button>
          <button mat-button class="media-btn" (click)="videoInput.click()" [disabled]="images.length > 0">
            <mat-icon style="color:#f02849">videocam</mat-icon> Video
          </button>
        </div>
        <button
          mat-flat-button color="primary"
          class="post-btn"
          (click)="submit()"
          [disabled]="(!content.trim() && !images.length && !videoFile) || loading"
        >
          <mat-spinner diameter="16" *ngIf="loading"></mat-spinner>
          <span *ngIf="!loading">Post</span>
        </button>
      </div>

      <input #imageInput type="file" accept="image/jpeg,image/png,image/webp,image/gif" multiple hidden (change)="onImagesSelected($event)" />
      <input #videoInput type="file" accept="video/mp4,video/quicktime,video/webm" hidden (change)="onVideoSelected($event)" />
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    .create-post { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
    .create-top { display: flex; align-items: flex-start; gap: 10px; }
    .textarea-wrapper { flex: 1; position: relative; }
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
      box-sizing: border-box;
      &::placeholder { color: var(--text-secondary); }
      &:focus-visible { box-shadow: var(--shadow-glow); }
    }
    .textarea-wrapper.expanded .post-textarea { border-radius: 8px; min-height: 80px; }
    .mention-list {
      position: absolute; left: 0; right: 0; top: 100%; z-index: 20; margin: 4px 0 0; padding: 4px;
      list-style: none; background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
      box-shadow: var(--shadow-md); max-height: 240px; overflow-y: auto;
      li { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 6px; cursor: pointer; }
      li.active, li:hover { background: var(--primary-light); }
      .m-name { font-weight: 600; font-size: 14px; }
      .m-user { color: var(--text-secondary); font-size: 13px; }
      .avatar.xs { width: 24px; height: 24px; border-radius: 50%; object-fit: cover; }
    }
    .draft-images { display: flex; flex-wrap: wrap; gap: 8px; list-style: none; margin: 0; padding: 0; }
    .draft-images li { position: relative; width: 104px; cursor: grab; }
    .draft-images li.dragging { opacity: .5; }
    .draft-images img { width: 104px; height: 104px; object-fit: cover; border-radius: 8px; display: block; border: 1px solid var(--border); }
    .order-badge {
      position: absolute; top: 4px; left: 4px; background: rgba(0,0,0,.6); color: #fff; font-size: 11px;
      border-radius: 10px; padding: 0 6px; line-height: 18px;
    }
    .thumb-actions {
      display: flex; justify-content: space-between; margin-top: 2px;
      button {
        border: none; background: var(--bg); border-radius: 4px; cursor: pointer; width: 24px; height: 24px; padding: 0;
        display: flex; align-items: center; justify-content: center; color: var(--text-primary);
        &:disabled { opacity: .35; cursor: default; }
        &:focus-visible { outline: 2px solid var(--primary); }
        mat-icon { font-size: 16px; width: 16px; height: 16px; }
      }
    }
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
    .error { color: var(--danger); font-size: 13px; margin: 0; }
    .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; }
    .create-actions { display: flex; justify-content: space-between; align-items: center; border-top: 1px solid var(--border); padding-top: 12px; }
    .media-btns { display: flex; gap: 4px; }
    .media-btn { border-radius: 8px; }
    .post-btn { min-width: 80px; display: flex; align-items: center; gap: 6px; }
  `]
})
export class CreatePostComponent implements OnInit, OnDestroy {
  @Input() currentUser: User | null = null;
  /** When set, the post is published into this group. */
  @Input() groupId: number | null = null;
  /** When set, the post is published as this page (the server checks you're one of its admins or editors). */
  @Input() pageId: number | null = null;
  @Output() postCreated = new EventEmitter<Post>();
  @ViewChild('textarea') textarea!: ElementRef<HTMLTextAreaElement>;

  content = '';
  expanded = false;
  loading = false;
  error = '';
  maxImages = MAX_IMAGES;
  images: DraftImage[] = [];
  videoFile: File | null = null;
  videoUrl: string | null = null;
  dragFrom: number | null = null;
  liveMessage = '';

  mentionResults: User[] = [];
  mentionIndex = 0;
  private mentionQuery$ = new Subject<string>();
  private mentionSub?: Subscription;

  get placeholder(): string {
    return `What's on your mind, ${this.currentUser?.first_name || 'you'}?`;
  }

  constructor(private apiService: ApiService, private dialog: MatDialog) {}

  ngOnInit(): void {
    // The user search API already hides blocked and unsearchable accounts.
    this.mentionSub = this.mentionQuery$.pipe(
      debounceTime(200),
      distinctUntilChanged(),
      switchMap((q) => q
        ? this.apiService.searchUsers(q).pipe(map((r) => r.results.slice(0, 6)), catchError(() => of([] as User[])))
        : of([] as User[])),
    ).subscribe((users) => {
      this.mentionResults = users;
      this.mentionIndex = 0;
    });
  }

  ngOnDestroy(): void {
    this.mentionSub?.unsubscribe();
    this.clearMedia();
  }

  // ── Mentions ────────────────────────────────────────────────────────────

  private mentionMatch(): RegExpMatchArray | null {
    const el = this.textarea?.nativeElement;
    if (!el) return null;
    return el.value.slice(0, el.selectionStart ?? 0).match(MENTION_AT_CARET);
  }

  onTextInput(): void {
    const m = this.mentionMatch();
    this.mentionQuery$.next(m ? m[1] : '');
    if (!m) this.mentionResults = [];
  }

  onTextKeydown(event: KeyboardEvent): void {
    if (!this.mentionResults.length) return;
    const n = this.mentionResults.length;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      this.mentionIndex = (this.mentionIndex + 1) % n;
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      this.mentionIndex = (this.mentionIndex - 1 + n) % n;
    } else if (event.key === 'Enter' || event.key === 'Tab') {
      event.preventDefault();
      this.insertMention(this.mentionResults[this.mentionIndex]);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      this.closeMentions();
    }
  }

  insertMention(user: User): void {
    const el = this.textarea.nativeElement;
    const caret = el.selectionStart ?? el.value.length;
    const m = el.value.slice(0, caret).match(MENTION_AT_CARET);
    if (!m) return;
    const start = caret - m[1].length - 1;
    const insert = `@${user.username} `;
    this.content = el.value.slice(0, start) + insert + el.value.slice(caret);
    this.closeMentions();
    setTimeout(() => {
      el.focus();
      el.setSelectionRange(start + insert.length, start + insert.length);
    });
  }

  closeMentions(): void {
    this.mentionResults = [];
    this.mentionQuery$.next('');
  }

  closeMentionsSoon(): void {
    setTimeout(() => this.closeMentions(), 150);
  }

  // ── Media ───────────────────────────────────────────────────────────────

  onImagesSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const files = Array.from(input.files ?? []).filter((f) => f.type.startsWith('image/'));
    const room = MAX_IMAGES - this.images.length;
    if (files.length > room) this.error = `You can add up to ${MAX_IMAGES} images.`;
    for (const file of files.slice(0, room)) {
      this.images.push({ file, url: URL.createObjectURL(file) });
    }
    this.images = [...this.images];
    this.expanded = true;
    input.value = '';
  }

  onVideoSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (file) {
      this.removeVideo();
      this.videoFile = file;
      this.videoUrl = URL.createObjectURL(file);
      this.expanded = true;
    }
    input.value = '';
  }

  move(index: number, delta: number): void {
    const target = index + delta;
    if (target < 0 || target >= this.images.length) return;
    const copy = [...this.images];
    [copy[index], copy[target]] = [copy[target], copy[index]];
    this.images = copy;
    this.liveMessage = `Image moved to position ${target + 1} of ${copy.length}.`;
  }

  dropOn(index: number): void {
    if (this.dragFrom === null || this.dragFrom === index) {
      this.dragFrom = null;
      return;
    }
    const copy = [...this.images];
    const [moved] = copy.splice(this.dragFrom, 1);
    copy.splice(index, 0, moved);
    this.images = copy;
    this.dragFrom = null;
    this.liveMessage = `Image moved to position ${index + 1} of ${copy.length}.`;
  }

  crop(index: number): void {
    const img = this.images[index];
    const ref = this.dialog.open(ImageCropperComponent, {
      data: { file: img.file, aspectRatio: 0, title: 'Crop Image' },
      width: '550px',
    });
    ref.afterClosed().subscribe((result: ImageCropperResult | undefined) => {
      if (!result) return;
      URL.revokeObjectURL(img.url);
      const file = new File([result.blob], img.file.name, { type: 'image/jpeg' });
      const copy = [...this.images];
      copy[index] = { file, url: URL.createObjectURL(file) };
      this.images = copy;
    });
  }

  removeImageAt(index: number): void {
    URL.revokeObjectURL(this.images[index].url);
    this.images = this.images.filter((_, i) => i !== index);
    this.liveMessage = 'Image removed.';
  }

  removeVideo(): void {
    if (this.videoUrl) URL.revokeObjectURL(this.videoUrl);
    this.videoFile = null;
    this.videoUrl = null;
  }

  private clearMedia(): void {
    this.images.forEach((img) => URL.revokeObjectURL(img.url));
    this.images = [];
    this.removeVideo();
  }

  submit(): void {
    if (!this.content.trim() && !this.images.length && !this.videoFile) return;
    this.loading = true;
    this.error = '';

    const data = new FormData();
    data.append('content', this.content);
    if (this.groupId) data.append('group', String(this.groupId));
    if (this.pageId) data.append('page', String(this.pageId));
    if (this.videoFile) {
      data.append('post_type', 'video');
      data.append('video', this.videoFile);
    } else if (this.images.length) {
      data.append('post_type', 'image');
      this.images.forEach((img) => data.append('images', img.file));
    } else {
      data.append('post_type', 'text');
    }

    this.apiService.createPost(data).subscribe({
      next: (post) => {
        this.postCreated.emit(post);
        this.content = '';
        this.clearMedia();
        this.expanded = false;
        this.loading = false;
      },
      error: (err: HttpErrorResponse) => {
        this.loading = false;
        this.error = firstError(err.error) || 'Your post could not be published.';
      },
    });
  }
}
