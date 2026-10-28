import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';

/**
 * "Nothing here yet" panel for list pages. Project call-to-action buttons or links as content:
 *
 *   <app-empty-state icon="group" title="No groups yet" message="Join one to see it here.">
 *     <a mat-flat-button routerLink="/groups">Find groups</a>
 *   </app-empty-state>
 */
@Component({
  selector: 'app-empty-state',
  imports: [MatIconModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="state" [class.compact]="compact()">
      <div class="state-icon" aria-hidden="true"><mat-icon>{{ icon() }}</mat-icon></div>
      <h3 class="state-title">{{ title() }}</h3>
      @if (message()) {
        <p class="state-message">{{ message() }}</p>
      }
      <div class="state-actions"><ng-content></ng-content></div>
    </div>
  `,
  styleUrl: './states.scss',
})
export class EmptyStateComponent {
  readonly icon = input('inbox');
  readonly title = input.required<string>();
  readonly message = input('');
  /** Less padding, for use inside a sidebar or a tab. */
  readonly compact = input(false);
}
