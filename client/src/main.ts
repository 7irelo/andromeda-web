import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { AppComponent } from './app/app.component';
import { initErrorReporting } from './app/core/error-reporting';

initErrorReporting();

bootstrapApplication(AppComponent, appConfig)
  .catch((err) => console.error(err));
