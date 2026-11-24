import { Component, HostListener, inject, signal } from '@angular/core';
import { DatePipe, KeyValuePipe } from '@angular/common';
import { Store } from '../core/store.service';

/** Right pane: the selected item's media, details, fields and text. On small screens it slides over. */
@Component({
  selector: 'mm-detail',
  imports: [DatePipe, KeyValuePipe],
  host: { '[class.open]': '!!store.selected()' },
  template: `
    @if (store.selected(); as it) {
      <div class="media">
        @if (it.kind === 'video') {
          <video [src]="store.mediaUrl(it.media)" [poster]="it.thumb ? store.mediaUrl(it.thumb) : ''" controls playsinline></video>
        } @else {
          <img [src]="store.mediaUrl(it.media)" [alt]="it.title" />
        }
        <button class="close" (click)="close()" aria-label="Close details">✕</button>
      </div>
      <div class="body">
        <h2>{{ it.title }}</h2>
        <p class="sub"><span class="chip">{{ it.category }}</span>
          {{ it.kind === 'video' ? 'video' : 'image' }}@if (it.created_at) { · saved {{ it.created_at | date:'d MMM' }} } · record {{ it.id }}</p>
        <div class="tabs" role="tablist">
          <button role="tab" [class.on]="tab() === 'summary'" (click)="tab.set('summary')">Summary</button>
          <button role="tab" [class.on]="tab() === 'fields'" (click)="tab.set('fields')">Fields</button>
          <button role="tab" [class.on]="tab() === 'text'" (click)="tab.set('text')">{{ it.kind === 'video' ? 'Transcript' : 'Text' }}</button>
        </div>
        @switch (tab()) {
          @case ('summary') {
            <dl>
              <dt>Category</dt><dd>{{ it.category }}</dd>
              <dt>Type</dt><dd>{{ it.kind }}</dd>
              <dt>Tags</dt><dd>@for (t of it.tags; track t) { <span class="chip">{{ t }}</span> } @empty { none }</dd>
              @if (it.confidence != null) { <dt>Confidence</dt><dd>{{ it.confidence }}</dd> }
              <dt>Record</dt><dd>{{ it.id }}</dd>
            </dl>
          }
          @case ('fields') {
            @if (hasFields(it.fields)) {
              <dl>@for (f of it.fields | keyvalue; track f.key) { <dt>{{ f.key }}</dt><dd>{{ show(f.value) }}</dd> }</dl>
            } @else { <p class="none">No extracted fields yet. The extraction agent fills these (Role 3).</p> }
          }
          @case ('text') {
            @if (it.text) { <p class="text">{{ it.text }}</p> }
            @else { <p class="none">No {{ it.kind === 'video' ? 'transcript' : 'text' }} yet. The reader fills this (Role 2).</p> }
          }
        }
        <div class="actions">
          <button class="btn ghost" disabled title="Comes with the Organizer agent; every change will wait for approval">Edit</button>
          <button class="btn ghost" disabled title="Comes with the Organizer agent; every change will wait for approval">Move</button>
          <button class="btn danger" (click)="store.proposeDelete(it)" [disabled]="store.deletePending(it.id)"
                  title="Proposes the delete; nothing is removed until you approve it">Delete</button>
          <span class="needs">{{ store.deletePending(it.id) ? 'delete waiting in Approvals' : 'needs approval' }}</span>
        </div>
      </div>
    } @else {
      <p class="pick">Select an item to see its media, fields and text.</p>
    }`,
  styles: `
    :host { display: flex; flex-direction: column; overflow-y: auto; background: var(--surface); border-left: 1px solid var(--border); }
    .media { position: relative; background: var(--media-bg); }
    .media img, .media video { width: 100%; max-height: 340px; object-fit: contain; display: block; background: var(--media-bg); }
    .close { display: none; position: absolute; top: 8px; right: 8px; border: 0; width: 32px; height: 32px; border-radius: 50%;
      background: #0008; color: #fff; }
    .body { padding: 16px 18px 20px; display: grid; gap: 12px; }
    h2 { margin: 0; font-size: 17px; line-height: 1.3; }
    .sub { margin: 0; color: var(--muted); font-size: 13px; }
    .tabs { display: flex; gap: 18px; border-bottom: 1px solid var(--border); }
    .tabs button { border: 0; background: none; padding: 6px 0; color: var(--muted); border-bottom: 2px solid transparent; margin-bottom: -1px; }
    .tabs button.on { color: var(--text); font-weight: 600; border-bottom-color: var(--brand); }
    dl { display: grid; grid-template-columns: 110px 1fr; gap: 8px 12px; margin: 0; }
    dt { color: var(--muted); text-transform: capitalize; } dd { margin: 0; text-transform: none; }
    .text { margin: 0; white-space: pre-wrap; line-height: 1.55; }
    .none, .pick { color: var(--muted); margin: 0; }
    .pick { padding: 40px 24px; text-align: center; }
    .actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; padding-top: 4px; }
    .needs { color: var(--warm); font-size: 12.5px; margin-left: auto; }
    @media (max-width: 1100px) {
      :host { position: fixed; top: 0; right: 0; bottom: 0; width: min(420px, 100vw); z-index: 25; border-left: 1px solid var(--border);
        box-shadow: -8px 0 24px #0003; transform: translateX(100%); transition: transform .2s; }
      :host(.open) { transform: none; }
      .close { display: block; } .pick { display: none; }
    }`,
})
export class Detail {
  store = inject(Store);
  tab = signal<'summary' | 'fields' | 'text'>('summary');
  close() { this.store.selected.set(null); }
  hasFields(f?: Record<string, unknown>) { return !!f && Object.keys(f).length > 0; }
  show(v: unknown) { return Array.isArray(v) ? v.join(', ') : typeof v === 'object' && v ? JSON.stringify(v) : String(v); }
  @HostListener('document:keydown.escape') esc() { this.close(); }
}
