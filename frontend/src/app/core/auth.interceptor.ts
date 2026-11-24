import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';
import { Session } from './session.service';

/** Any 401 (session expired, logged out in another tab) sends the user back to the login screen. */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const session = inject(Session);
  return next(req).pipe(catchError((e: unknown) => {
    if (e instanceof HttpErrorResponse && e.status === 401 && !req.url.includes('/auth/')) session.me.set(null);
    return throwError(() => e);
  }));
};
