import { Component, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Store } from '../core/store.service';

@Component({
  selector: 'mm-upload',
  imports: [FormsModule],
  template: `
    @if (open()) {
      <div class="scrim" (click)="closed.emit()">
        <form (click)="$event.stopPropagation()" (ngSubmit)="submit()" role="dialog" aria-label="Upload">
          <h2>Add to MediaMind</h2>
          <label class="drop">
            @if (preview(); as src) {
              @if (isVideo()) { <video [src]="src" muted controls playsinline></video> } @else { <img [src]="src" alt="preview" /> }
            } @else { <span>Choose a photo, screenshot or short video</span> }
            <input type="file" accept="image/png,image/jpeg,image/webp,video/mp4,video/webm" (change)="pick($event)" hidden />
          </label>
          <input name="title" [(ngModel)]="title" placeholder="Title (optional)" />
          <select name="cat" [(ngModel)]="category">
            @for (c of cats; track c) { <option [value]="c">{{ c }}</option> }
          </select>
          @if (error()) { <p class="err">{{ error() }}</p> }
          <p class="hint">It goes to your approval queue first. Nothing is saved until you approve.</p>
          <div class="row">
            <button type="button" class="btn ghost" (click)="closed.emit()">Cancel</button>
            <button class="btn" [disabled]="!file || busy()">{{ busy() ? 'Uploading…' : 'Propose save' }}</button>
          </div>
        </form>
      </div>
    }`,
  styles: `
    .scrim { position: fixed; inset: 0; background: #000b; z-index: 30; display: grid; place-items: center; padding: 16px; }
    form { background: var(--surface); border-radius: 14px; padding: 20px; width: min(420px, 100%); display: grid; gap: 12px; }
    h2 { margin: 0; font-size: 18px; }
    .drop { border: 2px dashed var(--border); border-radius: var(--radius); min-height: 150px; display: grid; place-items: center;
      color: var(--muted); cursor: pointer; overflow: hidden; } .drop img, .drop video { width: 100%; max-height: 240px; object-fit: cover; }
    input:not([hidden]), select { padding: 9px 10px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg); }
    .row { display: flex; justify-content: flex-end; gap: 8px; } .hint { color: var(--muted); font-size: 13px; margin: 0; }
    .err { color: var(--danger); margin: 0; }`,
})
export class Upload {
  store = inject(Store);
  open = input.required<boolean>();
  closed = output<void>();
  cats = ['recipe', 'workout', 'place', 'learning', 'other'];
  file: File | null = null;
  title = '';
  category = 'recipe';
  preview = signal<string | null>(null);
  isVideo = signal(false);
  error = signal<string | null>(null);
  busy = signal(false);

  pick(e: Event) {
    this.file = (e.target as HTMLInputElement).files?.[0] ?? null;
    this.isVideo.set(!!this.file?.type.startsWith('video/'));
    this.preview.set(this.file ? URL.createObjectURL(this.file) : null);
    if (this.file && !this.title) this.category = this.isVideo() ? 'workout' : this.category;
  }

  async submit() {
    if (!this.file) return;
    this.busy.set(true);
    const err = await this.store.upload(this.file, this.title, this.category);
    this.busy.set(false);
    this.error.set(err);
    if (!err) { this.file = null; this.title = ''; this.preview.set(null); this.closed.emit(); }
  }
}
