import { Injectable, signal } from '@angular/core';

/** Who is logged in. undefined = still checking, null = logged out (show the login screen). */
@Injectable({ providedIn: 'root' })
export class Session {
  readonly me = signal<string | null | undefined>(undefined);
  /** False when the server has login switched off (auth.required: false): no login screen, no Log out. */
  readonly loginEnabled = signal(true);
}
