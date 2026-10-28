import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from '../services/auth.service';

export const authGuard: CanActivateFn = (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (auth.isLoggedIn()) return true;

  // Come back here after signing in (e.g. a group invite link opened while signed out).
  return router.createUrlTree(['/login'], { queryParams: { returnUrl: state.url } });
};

/** Only same-app paths: never another origin ("//evil.example", "https://...", "/\\evil"). */
export function safeReturnUrl(raw: string | null | undefined): string {
  if (!raw || !raw.startsWith('/') || raw.startsWith('//') || raw.startsWith('/\\') || raw.startsWith('/login')) {
    return '/feed';
  }
  return raw;
}
