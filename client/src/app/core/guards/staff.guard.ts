import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from '../services/auth.service';

/** UI convenience only: the moderation API itself is staff-only on the server. */
export const staffGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  return auth.currentUser?.is_staff ? true : inject(Router).createUrlTree(['/feed']);
};
