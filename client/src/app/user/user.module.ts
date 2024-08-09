import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';

import { UserRoutingModule } from './user-routing.module';
import { UserProfileComponent } from './user-profile/user-profile.component';
import { UserListComponent } from './user-list/user-list.component';


@NgModule({
  declarations: [
    UserProfileComponent,
    UserListComponent
  ],
  imports: [
    CommonModule,
    UserRoutingModule
  ]
})
export class UserModule { }
