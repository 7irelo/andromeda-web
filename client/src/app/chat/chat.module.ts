import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';

import { ChatRoutingModule } from './chat-routing.module';
import { ChatListComponent } from './chat-list/chat-list.component';
import { ChatWindowComponent } from './chat-window/chat-window.component';


@NgModule({
  declarations: [
    ChatListComponent,
    ChatWindowComponent
  ],
  imports: [
    CommonModule,
    ChatRoutingModule
  ]
})
export class ChatModule { }
