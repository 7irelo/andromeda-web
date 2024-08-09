import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';

import { WatchRoutingModule } from './watch-routing.module';
import { WatchListComponent } from './watch-list/watch-list.component';
import { WatchDetailComponent } from './watch-detail/watch-detail.component';


@NgModule({
  declarations: [
    WatchListComponent,
    WatchDetailComponent
  ],
  imports: [
    CommonModule,
    WatchRoutingModule
  ]
})
export class WatchModule { }
