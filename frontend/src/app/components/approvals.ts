import { Component, inject, input, output, signal } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Proposal } from '../core/models';
import { Store } from '../core/store.service';

/** Human-in-the-loop queue. Nothing is written to the library until a person approves the exact payload. */
@Component({
  selector: 'mm-approvals',
  imports: [FormsModule, NgTemplateOutlet],
  template: `
    <ng-template #card let-p>
          @if (p.action === 'library.collect') {
          <div class="card">
            <span class="thumb folder" aria-hidden="true">▤</span>
            <div class="body">
              <div><span class="chip">{{ p.payload.existing ? 'add to collection' : 'new collection' }}</span>
                <span class="chip">{{ p.payload.item_ids?.length }} items</span>
                <code title="hash of the exact payload you are approving">#{{ p.hash.slice(0, 8) }}</code></div>
              <input [ngModel]="draft(p)" (ngModelChange)="setDraft(p, $event)" aria-label="Collection name" />
              <ul class="titles">
                @for (t of (p.payload.item_titles ?? []).slice(0, 4); track $index) { <li>{{ t }}</li> }
                @if ((p.payload.item_titles?.length ?? 0) > 4) { <li class="more">and {{ (p.payload.item_titles?.length ?? 0) - 4 }} more</li> }
              </ul>
              <div class="row">
                @if (dirty(p)) {
                  <button class="btn" (click)="store.edit(p, draft(p))">Save edit</button>
                } @else {
                  <button class="btn" (click)="store.approve(p)">Approve</button>
                }
                <button class="btn danger" (click)="store.reject(p)">Reject</button>
              </div>
              @if (dirty(p)) { <small>Editing changes the hash, so approve again after saving.</small> }
            </div>
          </div>
          } @else if (p.action === 'library.soft_delete') {
          <div class="card del">
            <span class="thumb">
              <img [src]="store.mediaUrl(p.payload.kind === 'video' && p.payload.thumb ? p.payload.thumb : p.payload.media!)" alt="the item to delete" />
              @if (p.payload.kind === 'video') { <b>▶</b> }
            </span>
            <div class="body">
              <div><span class="chip warn">delete</span><span class="chip">{{ p.payload.category }}</span>
                <code title="hash of the exact payload you are approving">#{{ p.hash.slice(0, 8) }}</code></div>
              <strong>{{ p.payload.title }}</strong>
              <small>Hidden from your library, search and collections. Kept in the database, so it can be restored.</small>
              <div class="row">
                <button class="btn danger" (click)="store.approve(p)">Approve delete</button>
                <button class="btn ghost" (click)="store.reject(p)">Keep it</button>
              </div>
            </div>
          </div>
          } @else {
          <div class="card">
            <span class="thumb">
              @if (p.payload.sha256) { <img [src]="store.previewUrl(p.id)" alt="what you are approving" /> }
              @if (p.payload.kind === 'video') { <b>▶</b> }
            </span>
            <div class="body">
              <div><span class="chip">save</span><span class="chip">{{ p.payload.category }}</span>
                @if (p.payload.kind === 'video') { <span class="chip">video · {{ p.payload.duration_s }} s</span> }
                <code title="hash of the exact payload you are approving">#{{ p.hash.slice(0, 8) }}</code></div>
              <input [ngModel]="draft(p)" (ngModelChange)="setDraft(p, $event)" aria-label="Title" />
              <div class="row">
                @if (dirty(p)) {
                  <button class="btn" (click)="store.edit(p, draft(p))">Save edit</button>
                } @else {
                  <button class="btn" (click)="store.approve(p)" [disabled]="!p.payload.sha256">Approve</button>
                }
                <button class="btn danger" (click)="store.reject(p)">Reject</button>
              </div>
              @if (dirty(p)) { <small>Editing changes the hash, so approve again after saving.</small> }
            </div>
          </div>
          }
    </ng-template>

    @if (store.focused(); as p) {
      <div class="scrim" (click)="store.later()"></div>
      <div class="modal" role="alertdialog" aria-modal="true" aria-label="Approve this change">
        <header><h2>{{ heading(p) }}</h2><button (click)="store.later()" aria-label="Decide later">✕</button></header>
        <p class="hint">Nothing happens until you approve this exact change.</p>
        <ng-container *ngTemplateOutlet="card; context: { $implicit: p }" />
        <button class="later" (click)="store.later()">Decide later (it stays in Approvals)</button>
      </div>
    }

    @if (open()) {
      <div class="scrim" (click)="closed.emit()"></div>
      <aside role="dialog" aria-label="Approvals">
        <header><h2>Approvals ({{ store.pending().length }})</h2><button (click)="closed.emit()" aria-label="Close">✕</button></header>
        <p class="hint">Every save, collection, edit, move and delete waits here for you.</p>
        @for (p of store.pending(); track p.id) {
          <ng-container *ngTemplateOutlet="card; context: { $implicit: p }" />
        } @empty { <p class="empty">All caught up.</p> }
      </aside>
    }`,
  styles: `
    .scrim { position: fixed; inset: 0; background: #0008; z-index: 20; }
    .modal { position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 31; width: min(460px, calc(100vw - 32px));
      max-height: calc(100vh - 32px); overflow: auto; background: var(--surface); border: 1px solid var(--border);
      border-radius: 14px; padding: 18px; box-shadow: 0 20px 60px #0006; }
    .modal + .scrim, .scrim:has(+ .modal) { z-index: 30; }
    .modal .card { margin: 10px 0 4px; }
    .later { border: 0; background: none; color: var(--muted); font-size: 13px; padding: 6px 0 0; cursor: pointer; text-decoration: underline; }
    aside { position: fixed; top: 0; right: 0; bottom: 0; width: min(380px, 100vw); z-index: 21; background: var(--surface);
      border-left: 1px solid var(--border); padding: 16px; overflow: auto; }
    header { display: flex; justify-content: space-between; align-items: center; } h2 { margin: 0; font-size: 18px; }
    header button { border: 0; background: none; font-size: 18px; color: var(--text); }
    .hint, .empty { color: var(--muted); font-size: 14px; }
    .card { display: flex; gap: 12px; border: 1px solid var(--border); border-radius: var(--radius); padding: 10px; margin: 12px 0; }
    .thumb { position: relative; width: 72px; height: 72px; border-radius: 6px; flex: none; overflow: hidden; background: var(--border); }
    .thumb img { width: 100%; height: 100%; object-fit: cover; }
    .thumb b { position: absolute; inset: 0; display: grid; place-items: center; color: #fff; text-shadow: 0 1px 4px #000; }
    .body { flex: 1; display: grid; gap: 8px; min-width: 0; } code { font-size: 12px; color: var(--muted); }
    input { width: 100%; padding: 7px 9px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg); }
    .row { display: flex; gap: 8px; } small { color: var(--muted); }
    .folder { display: grid; place-items: center; font-size: 30px; color: var(--brand); background: var(--brand-soft); }
    .chip.warn { background: color-mix(in srgb, var(--danger, #c2410c) 14%, transparent); color: var(--danger, #c2410c); }
    .del { border-color: color-mix(in srgb, var(--danger, #c2410c) 35%, var(--border)); }
    .titles { margin: 0; padding-left: 18px; font-size: 13px; display: grid; gap: 2px; } .more { color: var(--muted); }`,
})
export class Approvals {
  store = inject(Store);
  open = input.required<boolean>();
  closed = output<void>();
  drafts = signal<Record<string, string>>({});
  /** The editable field: a collection's name, or an upload's title. */
  private field(p: Proposal) { return (p.action === 'library.collect' ? p.payload.name : p.payload.title) ?? ''; }
  draft(p: Proposal) { return this.drafts()[p.id] ?? this.field(p); }
  setDraft(p: Proposal, v: string) { this.drafts.update(d => ({ ...d, [p.id]: v })); }
  dirty(p: Proposal) { return this.draft(p) !== this.field(p); }
  heading(p: Proposal) {
    return { 'library.collect': 'Save this collection?', 'library.soft_delete': 'Delete this item?' }[p.action] ?? 'Save this to your library?';
  }
}
