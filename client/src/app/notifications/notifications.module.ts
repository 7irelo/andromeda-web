import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';

import { NotificationsRoutingModule } from './notifications-routing.module';
import { NotificationListComponent } from './notification-list/notification-list.component';


@NgModule({
  declarations: [
    NotificationListComponent
  ],
  imports: [
    CommonModule,
    NotificationsRoutingModule
  ]
})
export class NotificationsModule { }
