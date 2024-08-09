import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';

import { PagesRoutingModule } from './pages-routing.module';
import { PageListComponent } from './page-list/page-list.component';
import { PageDetailComponent } from './page-detail/page-detail.component';


@NgModule({
  declarations: [
    PageListComponent,
    PageDetailComponent
  ],
  imports: [
    CommonModule,
    PagesRoutingModule
  ]
})
export class PagesModule { }
