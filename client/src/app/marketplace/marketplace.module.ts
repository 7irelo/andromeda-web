import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';

import { MarketplaceRoutingModule } from './marketplace-routing.module';
import { MarketListComponent } from './market-list/market-list.component';
import { MarketDetailComponent } from './market-detail/market-detail.component';


@NgModule({
  declarations: [
    MarketListComponent,
    MarketDetailComponent
  ],
  imports: [
    CommonModule,
    MarketplaceRoutingModule
  ]
})
export class MarketplaceModule { }
