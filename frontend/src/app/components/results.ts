import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CATEGORIES, Store } from '../core/store.service';

/** Middle pane: the collection as cards, or the chat answer with its cited results. */
@Component({
  selector: 'mm-results',
  imports: [FormsModule],
  template: `
    @if (store.error(); as e) { <p class="err">{{ e }}</p> }
    @if (store.answer(); as a) {
      <section class="chat">
        <div class="bubble">{{ store.query() }}</div>
        <p class="answer" [class.blocked]="a.blocked">{{ a.answer }}</p>
        @if (a.blocked) { <p class="why">Blocked by guardrail: {{ a.blocked }}</p> }
        <div class="list">
          @for (it of a.records; track it.id) {
            <button class="row" [class.on]="store.selected()?.id === it.id" (click)="store.selected.set(it)">
              <span class="thumb">
                @if (it.kind === 'video' && !it.thumb) { <span class="ph">▶</span> }
                @else { <img [src]="store.tileUrl(it)" alt="" loading="lazy" /> }
                @if (it.kind === 'video') { <span class="play">▶</span> }
              </span>
              <span class="meta"><b>{{ it.title }}</b>
                <small>{{ it.category }} · {{ it.kind === 'video' ? 'video' : 'image' }}</small>
                <small class="cited">cited as {{ it.id }}</small></span>
            </button>
          }
        </div>
        @if (a.citations.length) { <p class="cites">Cites {{ a.citations.join(' · ') }}</p> }
        @if (a.records.length && !a.blocked) {
          <button class="btn ghost save" (click)="store.saveResultsAsCollection()">
            Save {{ a.records.length }} result{{ a.records.length > 1 ? 's' : '' }} as collection “{{ store.query() }}”
          </button>
        }
      </section>
      <form class="followup" (ngSubmit)="follow()">
        <input name="f" [(ngModel)]="f" placeholder="Ask a follow-up question" aria-label="Ask a follow-up question" autocomplete="off" />
        <button class="send" [disabled]="!f.trim() || store.loading()" aria-label="Ask">➤</button>
      </form>
    } @else {
      <div class="head"><h2>{{ title() }}</h2><span class="caps">{{ store.items().length }} items</span></div>
      @if (!store.items().length && !store.error()) { <p class="empty">Nothing here yet. Use + Upload media.</p> }
      <div class="grid">
        @for (it of store.items(); track it.id) {
          <button class="card" [class.on]="store.selected()?.id === it.id" (click)="store.selected.set(it)" [attr.aria-label]="it.title">
            <span class="thumb">
              @if (it.kind === 'video' && !it.thumb) { <span class="ph">▶</span> }
              @else { <img [src]="store.tileUrl(it)" [alt]="it.title" loading="lazy" /> }
              @if (it.kind === 'video') { <span class="play">▶</span> }
            </span>
            <span class="meta"><b>{{ it.title }}</b><small>{{ it.category }} · {{ it.kind === 'video' ? 'video' : 'image' }}</small></span>
          </button>
        }
      </div>
    }`,
  styles: `
    :host { display: flex; flex-direction: column; overflow-y: auto; padding: 20px; gap: 12px; }
    .head { display: flex; align-items: baseline; justify-content: space-between; }
    h2 { margin: 0; font-size: 17px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 14px; }
    .card, .row { border: 1px solid var(--border); background: var(--surface); border-radius: var(--radius); padding: 0;
      color: var(--text); text-align: left; overflow: hidden; }
    .card { display: flex; flex-direction: column; }
    .card:hover, .row:hover { border-color: var(--brand); }
    .card.on, .row.on { border-color: var(--brand); box-shadow: 0 0 0 2px var(--brand-soft); }
    .thumb { position: relative; display: block; overflow: hidden; background: var(--media-bg); }
    .card .thumb { aspect-ratio: 4 / 3; }
    .thumb img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; object-position: top; display: block; }
    .play { position: absolute; left: 8px; bottom: 6px; color: #fff; font-size: 13px; text-shadow: 0 1px 3px #000; }
    .ph { display: grid; place-items: center; height: 100%; color: #fff; font-size: 26px; }
    .meta { display: grid; gap: 2px; padding: 10px 12px; } .meta b { font-size: 14px; line-height: 1.3; }
    small { color: var(--muted); text-transform: capitalize; } .cited { color: var(--brand); text-transform: none; }
    .chat { display: grid; gap: 12px; flex: 1; align-content: start; }
    .bubble { justify-self: end; background: var(--bg); border: 1px solid var(--border); border-radius: 16px 16px 4px 16px;
      padding: 8px 14px; max-width: 80%; }
    .answer { margin: 0; line-height: 1.5; } .answer.blocked { color: var(--danger); }
    .why { margin: 0; color: var(--danger); font-size: 13px; }
    .list { display: grid; gap: 10px; }
    .row { display: grid; grid-template-columns: 96px 1fr; align-items: stretch; }
    .row .thumb { min-height: 72px; }
    .cites { margin: 0; font-size: 12.5px; color: var(--muted); }
    .save { justify-self: start; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .followup { display: flex; gap: 8px; align-items: center; border: 1px solid var(--border); border-radius: 999px;
      padding: 4px 4px 4px 16px; background: var(--surface); position: sticky; bottom: 0; }
    .followup:focus-within { border-color: var(--brand); }
    .followup input { flex: 1; border: 0; outline: none; background: none; padding: 8px 0; min-width: 0; }
    .send { border: 0; width: 34px; height: 34px; border-radius: 50%; background: var(--brand); color: #fff; }
    .send:disabled { opacity: .5; }
    .empty, .err { color: var(--muted); text-align: center; padding: 40px 0; } .err { color: var(--danger); }
    @media (max-width: 720px) { :host { padding: 14px; } .grid { grid-template-columns: repeat(2, 1fr); gap: 10px; } }`,
})
export class Results {
  store = inject(Store);
  f = '';
  title() {
    return this.store.collection()?.name ?? CATEGORIES.find(c => c.id === this.store.category())?.label ?? 'All items';
  }
  follow() { const q = this.f.trim(); if (q) { this.f = ''; this.store.search(q); } }
}
