import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';

/** Failed-to-load panel with a retry button. Announced to screen readers as an alert. */
@Component({
  selector: 'app-error-state',
  imports: [MatIconModule, MatButtonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="state error" [class.compact]="compact()" role="alert">
      <div class="state-icon" aria-hidden="true"><mat-icon>{{ icon() }}</mat-icon></div>
      <h3 class="state-title">{{ title() || defaultTitle }}</h3>
      <p class="state-message">{{ message() || defaultMessage }}</p>
      <div class="state-actions">
        <button mat-stroked-button type="button" (click)="retry.emit()">
          <mat-icon aria-hidden="true">refresh</mat-icon>
          <span i18n="@@state.retry">Try again</span>
        </button>
        <ng-content></ng-content>
      </div>
    </div>
  `,
  styleUrl: './states.scss',
})
export class ErrorStateComponent {
  readonly icon = input('cloud_off');
  readonly title = input('');
  readonly message = input('');
  readonly compact = input(false);
  readonly retry = output<void>();

  protected readonly defaultTitle = $localize`:@@state.errorTitle:Something went wrong`;
  protected readonly defaultMessage = $localize`:@@state.errorMessage:We couldn't load this. Check your connection and try again.`;
}
