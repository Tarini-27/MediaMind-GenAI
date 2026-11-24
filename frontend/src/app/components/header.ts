import { Component, computed, effect, inject, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Store } from '../core/store.service';

/** Top bar: name, the question box (where the agent answers), upload. */
@Component({
  selector: 'mm-header',
  imports: [FormsModule],
  template: `
    <header>
      <span class="logo">MediaMind</span>
      <form class="search" (ngSubmit)="ask()" role="search">
        <span class="mag" aria-hidden="true">⌕</span>
        <input name="q" [ngModel]="q()" (ngModelChange)="q.set($event); pick.set(-1); focused.set(true)" autocomplete="off"
               aria-label="Ask about your saved media" placeholder="Ask about your saved media"
               role="combobox" [attr.aria-expanded]="showSuggest()" aria-controls="mm-suggest"
               (focus)="focused.set(true)" (blur)="focused.set(false)" (keydown)="key($event)" />
        @if (showSuggest()) {
          <div class="suggest" id="mm-suggest" role="listbox">
            <div class="shead"><span>Recent searches</span>
              <button type="button" (mousedown)="$event.preventDefault(); store.clearHistory()">Clear</button></div>
            @for (s of suggestions(); track s; let i = $index) {
              <button type="button" role="option" class="sitem" [class.on]="i === pick()" [attr.aria-selected]="i === pick()"
                      (mousedown)="$event.preventDefault(); choose(s)"><span class="clock" aria-hidden="true">↺</span>{{ s }}</button>
            }
          </div>
        }
        @if (q() || store.query()) {
          <button type="button" class="x" (click)="clear()" aria-label="Clear search">✕</button>
        }
      </form>
      <button class="btn upload" (click)="upload.emit()">+ Upload media</button>
      <div class="me">
        <span class="avatar" aria-hidden="true">{{ (store.session.me() ?? '?')[0].toUpperCase() }}</span>
        <span class="name">{{ store.session.me() }}</span>
        @if (store.session.loginEnabled()) { <button class="out" (click)="store.logout()">Log out</button> }
      </div>
    </header>`,
  styles: `
    header { height: 60px; display: flex; align-items: center; gap: 20px; padding: 0 20px;
      background: var(--surface); border-bottom: 1px solid var(--border); }
    .logo { font-size: 18px; font-weight: 700; letter-spacing: -.2px; color: var(--text); width: 180px; flex: none; }
    .search { position: relative; flex: 1; max-width: 560px; margin: 0 auto; display: flex; align-items: center; gap: 8px;
      border: 1px solid var(--border); border-radius: 999px; padding: 0 14px; background: var(--bg); }
    .search:focus-within { border-color: var(--brand); box-shadow: 0 0 0 3px var(--brand-soft); }
    .mag { color: var(--muted); font-size: 18px; }
    input { flex: 1; min-width: 0; border: 0; outline: none; background: none; padding: 9px 0; }
    input::placeholder { color: var(--muted); opacity: 1; }
    .x { border: 0; background: none; color: var(--muted); }
    .upload { flex: none; }
    .suggest { position: absolute; top: calc(100% + 6px); left: 0; right: 0; z-index: 15; background: var(--surface);
      border: 1px solid var(--border); border-radius: 14px; box-shadow: 0 12px 30px #0002; padding: 6px; }
    .shead { display: flex; justify-content: space-between; align-items: center; padding: 4px 10px 6px;
      font-size: 11.5px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
    .shead button { border: 0; background: none; color: var(--brand); font-size: 12px; cursor: pointer; text-transform: none; letter-spacing: 0; }
    .sitem { display: flex; gap: 10px; align-items: center; width: 100%; text-align: left; border: 0; background: none;
      padding: 8px 10px; border-radius: 8px; color: var(--text); font: inherit; cursor: pointer;
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .sitem:hover, .sitem.on { background: var(--brand-soft); }
    .clock { color: var(--muted); }
    .me { display: flex; align-items: center; gap: 8px; flex: none; }
    .avatar { width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center; font-weight: 700; font-size: 13px;
      background: var(--brand-soft); color: var(--brand); }
    .name { font-size: 14px; max-width: 110px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .out { border: 0; background: none; color: var(--muted); font-size: 13px; cursor: pointer; text-decoration: underline; }
    @media (max-width: 720px) { .logo { width: auto; font-size: 16px; } header { gap: 10px; padding: 0 12px; }
      .upload { padding: 8px 12px; } }
    @media (max-width: 900px) { .name { display: none; } }
    @media (max-width: 480px) { .logo { display: none; } .avatar { display: none; } }`,
})
export class Header {
  store = inject(Store);
  upload = output<void>();
  q = signal('');
  constructor() { effect(() => this.q.set(this.store.query())); }   // follow-up questions show here too
  ask() { this.focused.set(false); if (this.q().trim()) this.store.search(this.q()); }
  clear() { this.q.set(''); this.store.clearSearch(); this.focused.set(false); }

  // Suggestions: the user's own recent searches that contain what is typed, newest first.
  focused = signal(false);
  pick = signal(-1);
  suggestions = computed(() => {
    const t = this.q().trim().toLowerCase();
    return this.store.history().filter(s => s.toLowerCase() !== t && s.toLowerCase().includes(t)).slice(0, 6);
  });
  showSuggest = computed(() => this.focused() && this.suggestions().length > 0);
  choose(s: string) { this.q.set(s); this.pick.set(-1); this.focused.set(false); this.store.search(s); }
  key(e: KeyboardEvent) {
    if (!this.showSuggest()) return;
    const n = this.suggestions().length;
    if (e.key === 'ArrowDown') { e.preventDefault(); this.pick.set((this.pick() + 1) % n); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); this.pick.set((this.pick() - 1 + n) % n); }
    else if (e.key === 'Enter' && this.pick() >= 0) { e.preventDefault(); this.choose(this.suggestions()[this.pick()]); }
    else if (e.key === 'Escape') { this.focused.set(false); }
  }
}
