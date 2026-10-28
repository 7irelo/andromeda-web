import { APP_INITIALIZER, ApplicationConfig, isDevMode, provideZoneChangeDetection } from '@angular/core';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { provideHttpClient, withInterceptors, withXhr } from '@angular/common/http';
import { routes } from './app.routes';
import { authInterceptor } from './core/interceptors/auth.interceptor';
import { AuthService } from './core/services/auth.service';
import { provideServiceWorker } from '@angular/service-worker';

export const appConfig: ApplicationConfig = {
  providers: [
    // Components update plain fields from HTTP and socket callbacks and use Eager change
    // detection, so they need zone.js to know when to re-render. Angular 22 bootstraps
    // zoneless unless this is provided, and lists then stayed on their loading state.
    provideZoneChangeDetection({ eventCoalescing: true, runCoalescing: true }),
    provideRouter(routes, withComponentInputBinding()),
    // No provideAnimations(): nothing uses @angular/animations (Material animates with CSS and
    // honours prefers-reduced-motion itself), and the engine was ~75 kB of the initial bundle.
    provideHttpClient(withXhr(), withInterceptors([authInterceptor])),
    {
      // Resume the session from the HttpOnly refresh cookie before the first route guard runs.
      provide: APP_INITIALIZER,
      multi: true,
      deps: [AuthService],
      useFactory: (auth: AuthService) => () => auth.restoreSession(),
    },
    // Caches only the app shell and static assets (see ngsw-config.json): never API responses or media.
    provideServiceWorker('ngsw-worker.js', {
      enabled: !isDevMode(),
      registrationStrategy: 'registerWhenStable:30000',
    }),
  ],
};
