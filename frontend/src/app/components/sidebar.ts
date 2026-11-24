import { Component, inject, output } from '@angular/core';
import { CATEGORIES, Store } from '../core/store.service';

/** Left pane: collections with counts, and the approvals box. */
@Component({
  selector: 'mm-sidebar',
  template: `
    <nav aria-label="Collections">
      <div class="caps label">Collections</div>
      @for (c of cats; track c.id) {
        <button class="coll" [class.on]="store.category() === c.id && !store.answer() && !store.collection()" (click)="store.setCategory(c.id)">
          <span>{{ c.label }}</span><span class="n">{{ store.counts()[c.id] ?? 0 }}</span>
        </button>
      }
      <div class="caps label mine">My collections</div>
      @for (c of store.collections(); track c.id) {
        <button class="coll" [class.on]="store.collection()?.id === c.id && !store.answer()" (click)="store.openCollection(c)" [title]="c.name">
          <span class="nm">{{ c.name }}</span><span class="n">{{ c.count }}</span>
        </button>
      } @empty { <p class="hint">Search, then save the results as a collection.</p> }
    </nav>
    <button class="approvals" [class.has]="store.pending().length" (click)="approvals.emit()">
      <span class="row"><b>Approvals</b>
        @if (store.pending().length) { <span class="badge">{{ store.pending().length }}</span> }</span>
      <small>{{ summary() }}</small>
    </button>`,
  styles: `
    :host { display: flex; flex-direction: column; justify-content: space-between; gap: 16px; padding: 18px 12px;
      background: var(--surface); border-right: 1px solid var(--border); overflow-y: auto; }
    .label { padding: 0 10px 8px; } .mine { padding-top: 18px; }
    .nm { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding-right: 8px; }
    .hint { color: var(--muted); font-size: 12.5px; margin: 0; padding: 0 10px; }
    .coll { display: flex; justify-content: space-between; width: 100%; border: 0; background: none; color: var(--text);
      padding: 8px 10px; border-radius: 8px; text-align: left; }
    .coll:hover { background: var(--bg); }
    .coll.on { background: var(--brand-soft); color: var(--brand); font-weight: 600; }
    .n { color: var(--muted); font-variant-numeric: tabular-nums; } .on .n { color: var(--brand); }
    .approvals { text-align: left; border: 1px solid var(--border); background: var(--surface); color: var(--text);
      border-radius: var(--radius); padding: 12px; display: grid; gap: 4px; }
    .approvals.has { border-color: var(--warm); background: var(--warm-soft); }
    .row { display: flex; justify-content: space-between; align-items: center; }
    .badge { background: var(--warm); color: #fff; border-radius: 999px; font-size: 12px; min-width: 20px; padding: 1px 6px;
      text-align: center; font-weight: 700; }
    small { color: var(--muted); }
    @media (max-width: 720px) {
      :host { flex-direction: row; align-items: center; padding: 8px 12px; border-right: 0; border-bottom: 1px solid var(--border);
        overflow-x: auto; overflow-y: hidden; }
      nav { display: flex; gap: 6px; } .label, .hint { display: none; }
      .coll { width: auto; white-space: nowrap; gap: 8px; padding: 6px 12px; border: 1px solid var(--border); border-radius: 999px; }
      .approvals { flex: none; padding: 6px 12px; border-radius: 999px; } .approvals small { display: none; }
      .row { gap: 8px; }
    }`,
})
export class Sidebar {
  store = inject(Store);
  cats = CATEGORIES;
  approvals = output<void>();
  summary() {
    const p = this.store.pending();
    if (!p.length) return 'Nothing waiting';
    const saves = p.filter(x => x.action === 'library.save').length;
    const colls = p.filter(x => x.action === 'library.collect').length;
    const dels = p.filter(x => x.action === 'library.soft_delete').length;
    const other = p.length - saves - colls - dels;
    return [saves && `${saves} save${saves > 1 ? 's' : ''}`, colls && `${colls} collection${colls > 1 ? 's' : ''}`,
            dels && `${dels} delete${dels > 1 ? 's' : ''}`, other && `${other} other`].filter(Boolean).join(' · ');
  }
}
