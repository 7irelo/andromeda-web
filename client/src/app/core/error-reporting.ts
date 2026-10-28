import { ErrorHandler, Injectable } from '@angular/core';
import type { Breadcrumb, ErrorEvent } from '@sentry/angular';
import { environment } from '../../environments/environment';

/**
 * Browser error reporting (Sentry). Off unless a DSN was baked in at build
 * time (environment.sentryDsn). The SDK is loaded lazily, so builds without
 * a DSN never download it. Reports go to /api/errors/ on our own origin
 * (the CSP only allows connect-src 'self'), which relays them to Sentry.
 *
 * Nothing identifying is sent: no user, cookies, request bodies or query
 * strings (search terms, tokens), and no automatically collected user data.
 */

type Sentry = typeof import('@sentry/angular');

let sdk: Sentry | null = null;
const early: unknown[] = [];
const MAX_EARLY = 10;
const SENSITIVE_HEADERS = /^(authorization|cookie|x-csrftoken|x-api-key)$/i;

export function stripQuery(url: string): string {
  return url.split('#')[0].split('?')[0];
}

export function scrubEvent(event: ErrorEvent): ErrorEvent {
  delete event.user;
  const req = event.request;
  if (req) {
    delete req.cookies;
    delete req.data;
    delete req.query_string;
    if (req.url) {
      req.url = stripQuery(req.url);
    }
    if (req.headers) {
      for (const name of Object.keys(req.headers)) {
        if (SENSITIVE_HEADERS.test(name)) {
          delete req.headers[name];
        }
      }
    }
  }
  for (const crumb of event.breadcrumbs ?? []) {
    scrubBreadcrumb(crumb);
  }
  return event;
}

export function scrubBreadcrumb(crumb: Breadcrumb): Breadcrumb {
  const data = crumb.data;
  if (data) {
    for (const key of ['url', 'from', 'to']) {
      if (typeof data[key] === 'string') {
        data[key] = stripQuery(data[key] as string);
      }
    }
  }
  return crumb;
}

export function initErrorReporting(): void {
  const dsn = environment.sentryDsn;
  if (!dsn) {
    return;
  }
  import('@sentry/angular')
    .then((s) => {
      s.init({
        dsn,
        tunnel: '/api/errors/',
        environment: environment.production ? 'production' : 'development',
        // Collect nothing about the user or their requests; beforeSend scrubs again regardless.
        dataCollection: {
          userInfo: false,
          cookies: false,
          httpHeaders: false,
          httpBodies: [],
          urlQueryParams: false,
          stackFrameVariables: false,
          databaseQueryData: false,
          queues: false,
          graphQL: { document: false, variables: false },
          genAI: { inputs: false, outputs: false },
        },
        tracesSampleRate: 0,
        beforeSend: (event) => scrubEvent(event),
        beforeBreadcrumb: (crumb) => scrubBreadcrumb(crumb),
      });
      sdk = s;
      early.splice(0).forEach((error) => s.captureException(error));
    })
    .catch(() => {
      // Reporting is best effort; a blocked or failed chunk must never break the app.
    });
}

@Injectable()
export class ReportingErrorHandler implements ErrorHandler {
  handleError(error: unknown): void {
    console.error(error);
    if (!environment.sentryDsn) {
      return;
    }
    if (sdk) {
      sdk.captureException(error);
    } else if (early.length < MAX_EARLY) {
      early.push(error);
    }
  }
}
