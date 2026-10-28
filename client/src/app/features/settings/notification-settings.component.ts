import { Component, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatIconModule } from '@angular/material/icon';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { SwPush } from '@angular/service-worker';
import { ApiService } from '../../core/services/api.service';
import { NotificationCategory, NotificationPreferences } from '../../models/notification.model';

type Channel = 'in_app' | 'push' | 'email';

/** Per-category notification channels, the daily email digest and browser push. */
@Component({
    selector: 'app-notification-settings',
    imports: [CommonModule, MatButtonModule, MatCheckboxModule, MatIconModule, MatSlideToggleModule, MatSnackBarModule],
    template: `
    <section class="settings-section card" *ngIf="prefs">
      <h2><mat-icon>notifications</mat-icon> Notifications</h2>
      <table class="prefs" aria-label="Notification channels">
        <thead><tr><th scope="col">Category</th><th scope="col">In app</th><th scope="col">Push</th><th scope="col">Email</th></tr></thead>
        <tbody>
          <tr *ngFor="let c of prefs.categories">
            <th scope="row">{{ c.label }}</th>
            <td><mat-checkbox [checked]="c.in_app" [disabled]="c.locked" (change)="set(c, 'in_app', $event.checked)"
                  [attr.aria-label]="c.label + ' in app'"></mat-checkbox></td>
            <td><mat-checkbox [checked]="c.push" [disabled]="!prefs.push_available" (change)="set(c, 'push', $event.checked)"
                  [attr.aria-label]="c.label + ' push'"></mat-checkbox></td>
            <td><mat-checkbox [checked]="c.email" (change)="set(c, 'email', $event.checked)"
                  [attr.aria-label]="c.label + ' email'"></mat-checkbox></td>
          </tr>
        </tbody>
      </table>

      <mat-slide-toggle [checked]="prefs.email_digest === 'daily'" (change)="save({ email_digest: $event.checked ? 'daily' : 'off' })">
        Daily email of anything I haven't seen
      </mat-slide-toggle>
      <mat-slide-toggle [checked]="prefs.listing_digest" (change)="save({ listing_digest: $event.checked })">
        Weekly email of new marketplace listings near me
      </mat-slide-toggle>

      <div class="push" *ngIf="prefs.push_available && swPush.isEnabled">
        <button mat-stroked-button (click)="togglePush()">
          <mat-icon>{{ pushOn ? 'notifications_off' : 'notifications_active' }}</mat-icon>
          {{ pushOn ? 'Turn off push on this device' : 'Turn on push on this device' }}
        </button>
      </div>
      <p class="text-secondary text-sm" *ngIf="prefs.push_available && !swPush.isEnabled">
        Push notifications work once Andromeda is installed or opened from a secure (https) address.
      </p>
    </section>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    .settings-section { padding: 24px; margin-bottom: 16px; display: flex; flex-direction: column; gap: 12px; }
    .prefs { width: 100%; border-collapse: collapse; }
    .prefs th, .prefs td { padding: 4px 8px; text-align: center; }
    .prefs th[scope=row] { text-align: left; font-weight: 400; }
    .prefs thead th { font-size: 12px; opacity: .7; }
  `]
})
export class NotificationSettingsComponent implements OnInit {
  prefs: NotificationPreferences | null = null;
  pushOn = false;
  private endpoint: string | null = null;

  constructor(private api: ApiService, public swPush: SwPush, private snack: MatSnackBar) {}

  ngOnInit(): void {
    this.api.getNotificationPreferences().subscribe((p) => (this.prefs = p));
    if (this.swPush.isEnabled) {
      this.swPush.subscription.subscribe((sub) => {
        this.pushOn = !!sub;
        this.endpoint = sub?.endpoint ?? null;
      });
    }
  }

  set(c: NotificationCategory, channel: Channel, value: boolean): void {
    this.save({ categories: { [c.key]: { [channel]: value } } });
  }

  save(data: Parameters<ApiService['updateNotificationPreferences']>[0]): void {
    this.api.updateNotificationPreferences(data).subscribe({
      next: (p) => (this.prefs = p),
      error: () => this.snack.open('Could not save notification settings', 'Dismiss', { duration: 3000 }),
    });
  }

  async togglePush(): Promise<void> {
    try {
      if (this.pushOn) {
        if (this.endpoint) {
          this.api.deletePushSubscription(this.endpoint).subscribe();
        }
        await this.swPush.unsubscribe();
        return;
      }
      const key = await new Promise<string | null>((resolve) =>
        this.api.getPushPublicKey().subscribe({ next: (r) => resolve(r.public_key), error: () => resolve(null) }));
      if (!key) {
        return;
      }
      const sub = await this.swPush.requestSubscription({ serverPublicKey: key });
      this.api.savePushSubscription(sub.toJSON()).subscribe();
    } catch {
      this.snack.open('Push notifications were blocked by the browser', 'Dismiss', { duration: 4000 });
    }
  }
}
