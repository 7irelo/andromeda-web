import { HttpInterceptorFn, HttpRequest, HttpHandlerFn, HttpErrorResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, switchMap, throwError } from 'rxjs';
import { AuthService } from '../services/auth.service';
import { environment } from '../../../environments/environment';

// Auth endpoints that must never trigger a refresh-and-retry loop.
const NO_RETRY = ['/auth/token/refresh/', '/auth/login/', '/auth/register/', '/auth/logout/'];

export const authInterceptor: HttpInterceptorFn = (req: HttpRequest<unknown>, next: HttpHandlerFn) => {
  const authService = inject(AuthService);

  // Only ever attach the bearer token to our own API.
  const isApi = req.url.startsWith(environment.apiUrl) || req.url.startsWith('/api/');
  const withToken = (token: string | null) =>
    isApi && token ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }) : req;

  return next(withToken(authService.getAccessToken())).pipe(
    catchError((err: HttpErrorResponse) => {
      if (err.status !== 401 || !isApi || NO_RETRY.some((p) => req.url.includes(p))) {
        return throwError(() => err);
      }
      return authService.refreshAccessToken().pipe(
        switchMap((access) => next(withToken(access))),
        catchError(() => {
          authService.logout();
          return throwError(() => err);
        })
      );
    })
  );
};
