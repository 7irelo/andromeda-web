import { AfterViewInit, Directive, ElementRef, OnDestroy, inject, input, output } from '@angular/core';
import { FocusTrap, FocusTrapFactory } from '@angular/cdk/a11y';

/**
 * For hand-built modal panels (MatDialog already does all of this):
 * marks the element as a modal dialog, keeps Tab inside it, moves focus into it when
 * it opens, closes on Escape, and gives focus back to whatever opened it.
 *
 *   <div class="edit-dialog card" *ngIf="isCreating" appModalDialog
 *        dialogLabel="Create group" (dismiss)="cancelCreate()">
 */
@Directive({
  selector: '[appModalDialog]',
  host: {
    role: 'dialog',
    'aria-modal': 'true',
    '[attr.aria-label]': 'dialogLabel() || null',
    '(keydown.escape)': 'onEscape($event)',
  },
})
export class ModalDialogDirective implements AfterViewInit, OnDestroy {
  readonly dialogLabel = input('');
  readonly dismiss = output<void>();

  private readonly el = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly focusTrapFactory = inject(FocusTrapFactory);
  private focusTrap: FocusTrap | null = null;
  private readonly opener = (typeof document !== 'undefined' ? document.activeElement : null) as HTMLElement | null;

  ngAfterViewInit(): void {
    this.focusTrap = this.focusTrapFactory.create(this.el.nativeElement);
    // Prefer an element marked cdkFocusInitial, else the first focusable one.
    this.focusTrap.focusInitialElementWhenReady().then((moved) => {
      if (!moved) {
        this.el.nativeElement.setAttribute('tabindex', '-1');
        this.el.nativeElement.focus();
      }
    });
  }

  ngOnDestroy(): void {
    this.focusTrap?.destroy();
    if (this.opener?.isConnected) this.opener.focus();
  }

  onEscape(event: Event): void {
    event.stopPropagation();
    this.dismiss.emit();
  }
}
