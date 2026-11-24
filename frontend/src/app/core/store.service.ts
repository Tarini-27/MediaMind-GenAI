import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { ApiService } from './api.service';
import { Session } from './session.service';
import { AskResult, Category, Collection, Item, Proposal } from './models';

export const CATEGORIES: { id: Category; label: string }[] = [
  { id: 'all', label: 'All items' },
  { id: 'recipe', label: 'Recipes' },
  { id: 'workout', label: 'Workouts' },
  { id: 'place', label: 'Places' },
  { id: 'learning', label: 'Learning' },
  { id: 'other', label: 'Other' },
];

/** Single source of UI state (signals). Components read signals and call methods; no component talks to HTTP. */
@Injectable({ providedIn: 'root' })
export class Store {
  private api = inject(ApiService);
  readonly session = inject(Session);
  readonly history = signal<string[]>([]);           // recent searches, for suggestions under the search box

  readonly category = signal<Category>('all');
  readonly all = signal<Item[]>([]);                  // every saved item; categories are filtered from it
  readonly collections = signal<Collection[]>([]);    // the user's own named collections
  readonly collection = signal<Collection | null>(null);   // set while one is open
  readonly collectionItems = signal<Item[]>([]);
  readonly answer = signal<AskResult | null>(null);   // set while a search is active
  readonly query = signal('');
  readonly pending = signal<Proposal[]>([]);
  readonly selected = signal<Item | null>(null);      // shown in the detail pane
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly toast = signal<string | null>(null);

  /** Items in the chosen collection. */
  readonly items = computed(() => {
    if (this.collection()) return this.collectionItems();
    const c = this.category();
    return c === 'all' ? this.all() : this.all().filter(i => i.category === c);
  });
  /** Count per collection, for the sidebar. */
  readonly counts = computed(() => {
    const n: Record<string, number> = { all: this.all().length };
    for (const i of this.all()) n[i.category] = (n[i.category] ?? 0) + 1;
    return n;
  });
  /** What the middle pane shows: search hits while searching, otherwise the chosen collection. */
  readonly visible = computed(() => (this.answer() ? this.answer()!.records : this.items()));

  mediaUrl = (name: string) => this.api.mediaUrl(name);
  previewUrl = (proposalId: string) => this.api.previewUrl(proposalId);
  /** Card image: the thumbnail for videos, the file itself for images. */
  tileUrl = (it: Item) => this.api.mediaUrl(it.kind === 'video' && it.thumb ? it.thumb : it.media);

  /** Check the session cookie; load the library only when logged in. */
  async init() {
    try {
      const me = await firstValueFrom(this.api.me());
      this.session.loginEnabled.set(me.login);
      this.session.me.set(me.user_id);
    } catch {
      this.session.me.set(null);
      return;
    }
    await Promise.all([this.loadItems(), this.loadApprovals(), this.loadCollections(), this.loadHistory()]);
  }

  /** Returns an error message, or null on success. */
  async login(username: string, password: string, isNew: boolean): Promise<string | null> {
    try {
      await firstValueFrom(isNew ? this.api.signup(username, password) : this.api.login(username, password));
    } catch (e: any) {
      const d = e?.error?.detail;
      return typeof d === 'string' ? d : (e?.status === 0 ? 'The server is not reachable' : 'Could not log in');
    }
    this.reset();
    await this.init();
    return null;
  }

  async logout() {
    try { await firstValueFrom(this.api.logout()); } catch { /* cookie is cleared server-side if reachable */ }
    this.reset();
    this.session.me.set(null);
  }

  /** Forget everything of the previous user. */
  private reset() {
    this.all.set([]); this.collections.set([]); this.collection.set(null); this.collectionItems.set([]);
    this.answer.set(null); this.query.set(''); this.pending.set([]); this.selected.set(null);
    this.history.set([]); this.focus.set(null); this.category.set('all');
  }

  async loadHistory(q = '') {
    try { this.history.set(await firstValueFrom(this.api.history(q))); } catch { /* suggestions are optional */ }
  }

  async clearHistory() {
    try { await firstValueFrom(this.api.clearHistory()); this.history.set([]); } catch { this.notify('Could not clear history'); }
  }

  async loadCollections() {
    try {
      this.collections.set(await firstValueFrom(this.api.collections()));
    } catch { /* surfaced by loadItems */ }
  }

  async openCollection(c: Collection) {
    this.clearSearch();
    this.collection.set(c);
    this.collectionItems.set(await firstValueFrom(this.api.collectionItems(c.id)));
  }

  /** The proposal just made by the user: shown at once as a popup, so approving doesn't need a trip to the drawer. */
  readonly focus = signal<string | null>(null);
  readonly focused = computed(() => this.pending().find(p => p.id === this.focus()) ?? null);
  /** Close the popup; the proposal stays in the Approvals queue. */
  later() { this.focus.set(null); }

  /** True while a delete for this item is waiting in Approvals (so the button isn't pressed twice). */
  deletePending = (id: string) => this.pending().some(p => p.action === 'library.soft_delete' && p.payload.item_id === id);

  async proposeDelete(it: Item) {
    try {
      const r = await firstValueFrom(this.api.proposeDelete(it.id));
      await this.loadApprovals();
      this.focus.set(r.proposal_id);
    } catch (e: any) {
      this.notify(e?.error?.detail ?? 'Could not propose the delete');
    }
  }

  /** Propose saving the current search results as a collection named after the question. */
  async saveResultsAsCollection() {
    const a = this.answer();
    if (!a?.records.length) return;
    try {
      const r = await firstValueFrom(this.api.proposeCollection(this.query(), a.records.map(r => r.id)));
      await this.loadApprovals();
      this.focus.set(r.proposal_id);
    } catch (e: any) {
      this.notify(e?.error?.detail ?? 'Could not propose the collection');
    }
  }

  async loadItems() {
    try {
      this.all.set(await firstValueFrom(this.api.items('all')));
      this.error.set(null);
    } catch {
      this.error.set('Cannot reach the API. Is the backend running on port 8000?');
    }
  }

  async loadApprovals() {
    try {
      this.pending.set(await firstValueFrom(this.api.approvals()));
    } catch { /* surfaced by loadItems */ }
  }

  setCategory(c: Category) {
    this.category.set(c);
    this.collection.set(null);
    this.clearSearch();
  }

  async search(q: string) {
    this.query.set(q);
    if (!q.trim()) return this.clearSearch();
    this.loading.set(true);
    try {
      const a = await firstValueFrom(this.api.ask(q));
      this.answer.set(a);
      this.selected.set(a.records[0] ?? null);      // best match opens in the detail pane
      void this.loadHistory();
    } catch {
      this.notify('Search failed');
    } finally {
      this.loading.set(false);
    }
  }

  clearSearch() {
    this.query.set('');
    this.answer.set(null);
  }

  // ---- approvals
  async upload(file: File, title: string, category: string): Promise<string | null> {
    try {
      const p = await firstValueFrom(this.api.propose(file, title || file.name, category));
      try {
        await firstValueFrom(this.api.uploadBlob(p.proposal_id, file));
      } finally {
        await this.loadApprovals();   // a refused file is removed from the queue server-side
      }
      this.focus.set(p.proposal_id);
      return null;
    } catch (e: any) {
      return e?.error?.detail ?? 'Upload failed';
    }
  }

  async approve(p: Proposal) {
    this.later();
    try {
      await firstValueFrom(this.api.approve(p.id));
      this.notify({ 'library.collect': 'Collection saved', 'library.soft_delete': 'Deleted' }[p.action] ?? 'Saved to your library');
      if (p.action === 'library.soft_delete') {
        const gone = p.payload.item_id;
        if (this.selected()?.id === gone) this.selected.set(null);
        const a = this.answer();
        if (a) this.answer.set({ ...a, records: a.records.filter(r => r.id !== gone) });
      }
      await Promise.all([this.loadApprovals(), this.loadItems(), this.loadCollections()]);
      const open = this.collection();
      if (open) await this.openCollection(this.collections().find(c => c.id === open.id) ?? open);
    } catch (e: any) {
      this.notify(e?.error?.detail ?? 'Approval failed');
      await this.loadApprovals();
    }
  }

  /** Editing changes the payload hash, so any earlier approval is void and the item stays pending. */
  async edit(p: Proposal, value: string) {
    const field = p.action === 'library.collect' ? 'name' : 'title';
    await firstValueFrom(this.api.edit(p.id, { ...p.payload, [field]: value }));
    this.notify('Edited. Earlier approval is void; approve the new version.');
    await this.loadApprovals();
  }

  async reject(p: Proposal) {
    if (this.focus() === p.id) this.later();
    await firstValueFrom(this.api.reject(p.id));
    this.notify('Rejected, nothing saved');
    await this.loadApprovals();
  }

  notify(msg: string) {
    this.toast.set(msg);
    setTimeout(() => this.toast.set(null), 3500);
  }
}
