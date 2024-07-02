import { Injectable } from '@angular/core';
import { CanActivate, ActivatedRouteSnapshot, RouterStateSnapshot, UrlTree, Router } from '@angular/router';
import { Observable } from 'rxjs';
import { AuthService } from './auth.service';
import { map, tap, catchError } from 'rxjs/operators';

@Injectable({
  providedIn: 'root'
})
export class AuthGuard implements CanActivate {
  constructor(private authService: AuthService, private router: Router) {}

  canActivate(
    route: ActivatedRouteSnapshot,
    state: RouterStateSnapshot
  ): Observable<boolean | UrlTree> {
    return this.authService.checkAuth().pipe(
      map(isAuthenticated => {
        if (isAuthenticated) {
          return true;
        } else {
          console.log('Not authenticated - redirecting to login');
          return this.router.createUrlTree(['/login']);
        }
      }),
      catchError(error => {
        console.error('Error checking authentication status', error);
        return this.router.createUrlTree(['/login']);
      })
    );
  }
}
