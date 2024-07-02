import { HttpClientModule } from '@angular/common/http';
import { NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';

import { AppRoutingModule } from './app-routing.module';
import { AppComponent } from './app.component';
import { RegisterComponent } from '.register/register.component';
import { LoginComponent } from '.login/login.component';
import { ProfileComponent } from './profile/profile.component';
import { ProductListComponent } from './marketplace/marketplace/marketplace.component';
import { ProductDetailComponent } from './marketplace/product/product.component';
import { MarketplaceService } from './services/marketplace.service';
import { NavComponent } from './nav/nav.component';
import { FormsModule } from '@angular/forms';
import { HomeComponent } from '.home/home.component';
import { ReactiveFormsModule } from '@angular/forms';
import { AuthService } from './auth.service';
import { AuthGuard } from './auth.guard';
import { Emitters } from './emitters/emitters';

import { PostService } from './post.service';

@NgModule({
  declarations: [
    AppComponent,
    RegisterComponent,
    LoginComponent,
    HomeComponent
    ProfileComponent
    NavComponent
    MarketplaceComponent,
    ProductComponent
  ],
  imports: [
    BrowserModule, HttpClientModule,
    AppRoutingModule,
    FormsModule,
    ReactiveFormsModule,
    HttpClientModule
  ],
  providers: [AuthService, AuthGuard, Emitters, MarketplaceService],
  bootstrap: [AppComponent]
})
export class AppModule { }
