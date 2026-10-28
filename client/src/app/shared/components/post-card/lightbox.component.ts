import {
  AfterViewInit, ChangeDetectionStrategy, Component, ElementRef, EventEmitter, HostListener, Input, OnDestroy,
  Output, ViewChild,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';

/**
 * Full-screen image viewer. Keyboard: Esc closes, Left/Right move between
 * images, Tab stays inside the dialog, and focus returns to whatever opened it.
 */
@Component({
  selector: 'app-lightbox',
  imports: [CommonModule, MatIconModule],
  changeDetection: ChangeDetectionStrategy.Eager,
  template: `
    <div class="lightbox" role="dialog" aria-modal="true" [attr.aria-label]="label" (click)="closed.emit()" #root>
      <button type="button" class="lb-btn close" (click)="closed.emit()" aria-label="Close image viewer" #closeBtn>
        <mat-icon>close</mat-icon>
      </button>
      <button type="button" class="lb-btn prev" *ngIf="images.length > 1" (click)="step(-1, $event)"
              aria-label="Previous image">
        <mat-icon>chevron_left</mat-icon>
      </button>
      <figure (click)="$event.stopPropagation()">
        <img [src]="images[index]" [alt]="'Image ' + (index + 1) + ' of ' + images.length" />
        <figcaption *ngIf="images.length > 1" aria-live="polite">{{ index + 1 }} / {{ images.length }}</figcaption>
      </figure>
      <button type="button" class="lb-btn next" *ngIf="images.length > 1" (click)="step(1, $event)"
              aria-label="Next image">
        <mat-icon>chevron_right</mat-icon>
      </button>
    </div>
  `,
  styles: [`
    .lightbox {
      position: fixed; inset: 0; z-index: 2000; background: rgba(0,0,0,.9);
      display: flex; align-items: center; justify-content: center;
    }
    figure { margin: 0; display: flex; flex-direction: column; align-items: center; gap: 8px; }
    img { max-width: 92vw; max-height: 86vh; object-fit: contain; border-radius: 4px; }
    figcaption { color: #e2e8f0; font-size: 13px; }
    .lb-btn {
      position: absolute; background: rgba(255,255,255,.12); color: #fff; border: none; border-radius: 50%;
      width: 44px; height: 44px; display: flex; align-items: center; justify-content: center; cursor: pointer;
      &:hover, &:focus-visible { background: rgba(255,255,255,.25); outline: 2px solid #fff; }
    }
    .close { top: 16px; right: 16px; }
    .prev { left: 16px; top: 50%; transform: translateY(-50%); }
    .next { right: 16px; top: 50%; transform: translateY(-50%); }
  `],
})
export class LightboxComponent implements AfterViewInit, OnDestroy {
  @Input() images: string[] = [];
  @Input() index = 0;
  @Output() closed = new EventEmitter<void>();
  @ViewChild('closeBtn') closeBtn!: ElementRef<HTMLButtonElement>;
  @ViewChild('root') root!: ElementRef<HTMLElement>;

  private opener: HTMLElement | null = null;

  get label(): string {
    return this.images.length > 1 ? `Image viewer, ${this.images.length} images` : 'Image viewer';
  }

  ngAfterViewInit(): void {
    this.opener = document.activeElement as HTMLElement | null;
    this.closeBtn.nativeElement.focus();
  }

  ngOnDestroy(): void {
    this.opener?.focus?.();
  }

  step(delta: number, event?: Event): void {
    event?.stopPropagation();
    const n = this.images.length;
    if (n) this.index = (this.index + delta + n) % n;
  }

  @HostListener('document:keydown', ['$event'])
  onKey(event: KeyboardEvent): void {
    if (event.key === 'Escape') {
      event.preventDefault();
      this.closed.emit();
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      this.step(1);
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault();
      this.step(-1);
    } else if (event.key === 'Tab') {
      // Keep focus inside the dialog.
      const buttons = Array.from(this.root.nativeElement.querySelectorAll<HTMLElement>('button'));
      if (!buttons.length) return;
      const i = buttons.indexOf(document.activeElement as HTMLElement);
      const next = event.shiftKey ? (i <= 0 ? buttons.length - 1 : i - 1) : (i + 1) % buttons.length;
      event.preventDefault();
      buttons[next].focus();
    }
  }
}
