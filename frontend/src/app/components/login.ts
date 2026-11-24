import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Store } from '../core/store.service';

/** Log in or sign up. The server sets an HttpOnly session cookie; this page never sees or stores a token. */
@Component({
  selector: 'mm-login',
  imports: [FormsModule],
  template: `
    <main>
      <form class="card" (ngSubmit)="submit()">
        <h1>MediaMind</h1>
        <p class="tag">Search your saved photos, screenshots and short videos.</p>
        <div class="tabs" role="tablist">
          <button type="button" role="tab" [class.on]="!isNew()" [attr.aria-selected]="!isNew()" (click)="mode(false)">Log in</button>
          <button type="button" role="tab" [class.on]="isNew()" [attr.aria-selected]="isNew()" (click)="mode(true)">Sign up</button>
        </div>
        <label>Username
          <input name="u" [(ngModel)]="username" autocomplete="username" autocapitalize="none" required />
        </label>
        <label>Password
          <input name="p" type="password" [(ngModel)]="password" [attr.autocomplete]="isNew() ? 'new-password' : 'current-password'" required />
        </label>
        @if (isNew()) { <small>3 to 32 characters (letters, digits, . _ -), password at least 8.</small> }
        @if (error()) { <p class="err" role="alert">{{ error() }}</p> }
        <button class="btn" [disabled]="busy() || !username || !password">
          {{ busy() ? 'Please wait…' : isNew() ? 'Create account' : 'Log in' }}
        </button>
        @if (!isNew()) { <p class="demo">Sample library: <b>demo</b> / <b>mediamind-demo</b></p> }
      </form>
    </main>`,
  styles: `
    main { min-height: 100vh; display: grid; place-items: center; padding: 16px; background: var(--bg); }
    .card { width: min(380px, 100%); display: grid; gap: 14px; padding: 28px; background: var(--surface);
      border: 1px solid var(--border); border-radius: 16px; box-shadow: 0 10px 40px #0001; }
    h1 { margin: 0; font-size: 24px; } .tag { margin: -6px 0 4px; color: var(--muted); font-size: 14px; }
    .tabs { display: grid; grid-template-columns: 1fr 1fr; background: var(--bg); border-radius: 10px; padding: 3px; }
    .tabs button { border: 0; background: none; padding: 8px; border-radius: 8px; color: var(--muted); font: inherit; cursor: pointer; }
    .tabs .on { background: var(--surface); color: var(--text); font-weight: 600; box-shadow: 0 1px 3px #0002; }
    label { display: grid; gap: 6px; font-size: 13px; color: var(--muted); }
    input { padding: 10px 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--bg); color: var(--text); font: inherit; }
    input:focus { outline: none; border-color: var(--brand); box-shadow: 0 0 0 3px var(--brand-soft); }
    small, .demo { color: var(--muted); font-size: 12.5px; margin: 0; } .demo { text-align: center; }
    .err { margin: 0; color: var(--danger); font-size: 13.5px; }
    .btn { padding: 11px; }`,
})
export class Login {
  store = inject(Store);
  isNew = signal(false);
  busy = signal(false);
  error = signal<string | null>(null);
  username = '';
  password = '';
  mode(isNew: boolean) { this.isNew.set(isNew); this.error.set(null); }
  async submit() {
    this.busy.set(true);
    this.error.set(await this.store.login(this.username, this.password, this.isNew()));
    this.busy.set(false);
    if (!this.error()) this.password = '';
  }
}
