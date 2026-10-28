import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

export type SkeletonVariant = 'list' | 'card' | 'avatar' | 'post' | 'grid';

/**
 * Placeholder shapes shown while a list loads. Announces "Loading" once to assistive tech
 * (the shapes themselves are hidden from it). The shimmer stops under prefers-reduced-motion.
 */
@Component({
  selector: 'app-skeleton',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { role: 'status', '[attr.aria-busy]': 'true', '[class]': '"sk sk-" + variant()' },
  template: `
    <span class="visually-hidden">{{ label() || defaultLabel }}</span>
    @for (i of items(); track i) {
      @switch (variant()) {
        @case ('avatar') {
          <span class="skeleton sk-circle" aria-hidden="true"></span>
        }
        @case ('list') {
          <div class="sk-row" aria-hidden="true">
            <span class="skeleton sk-circle"></span>
            <div class="sk-lines">
              <span class="skeleton sk-line w60"></span>
              <span class="skeleton sk-line w40"></span>
            </div>
          </div>
        }
        @case ('post') {
          <div class="sk-card card" aria-hidden="true">
            <div class="sk-row">
              <span class="skeleton sk-circle"></span>
              <div class="sk-lines">
                <span class="skeleton sk-line w40"></span>
                <span class="skeleton sk-line w20"></span>
              </div>
            </div>
            <span class="skeleton sk-line w90"></span>
            <span class="skeleton sk-line w70"></span>
            <span class="skeleton sk-media"></span>
          </div>
        }
        @default {
          <div class="sk-card card" aria-hidden="true">
            <span class="skeleton sk-media"></span>
            <span class="skeleton sk-line w70"></span>
            <span class="skeleton sk-line w40"></span>
          </div>
        }
      }
    }
  `,
  styleUrl: './skeleton.component.scss',
})
export class SkeletonComponent {
  readonly variant = input<SkeletonVariant>('list');
  readonly count = input(3);
  readonly label = input('');

  protected readonly items = computed(() => Array.from({ length: Math.max(1, this.count()) }, (_, i) => i));
  protected readonly defaultLabel = $localize`:@@state.loading:Loading…`;
}
