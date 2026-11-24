import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { AskResult, Collection, Item, Proposal, ProposeResult } from './models';

/** Thin typed wrapper over the FastAPI endpoints. `/api` is proxied (dev) or reverse-proxied (nginx). */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  // No user_id is sent: the server takes the user from the HttpOnly session cookie, which the browser adds itself.

  mediaUrl(name: string): string {
    return `/api/media/${encodeURIComponent(name)}`;
  }

  /** Owner-only preview of a file that is still waiting for approval (videos return their thumbnail). */
  previewUrl(proposalId: string): string {
    return `/api/uploads/${proposalId}/preview`;
  }

  me() { return this.http.get<{ user_id: string; login: boolean }>('/api/auth/me'); }
  login(username: string, password: string) {
    return this.http.post<{ user_id: string }>('/api/auth/login', { username, password });
  }
  signup(username: string, password: string) {
    return this.http.post<{ user_id: string }>('/api/auth/signup', { username, password });
  }
  logout() { return this.http.post('/api/auth/logout', {}); }

  /** Recent searches, newest first, starting with or containing what is typed. */
  history(q: string) { return this.http.get<string[]>('/api/history', { params: { q } }); }
  clearHistory() { return this.http.delete('/api/history'); }

  items(category: string) {
    return this.http.get<Item[]>('/api/items', { params: { category } });
  }

  collectionItems(collectionId: string) {
    return this.http.get<Item[]>('/api/items', { params: { collection: collectionId } });
  }

  collections() {
    return this.http.get<Collection[]>('/api/collections');
  }

  /** A proposal only: the item stays until a person approves the delete. */
  proposeDelete(itemId: string) {
    return this.http.post<ProposeResult>(`/api/items/${encodeURIComponent(itemId)}/delete`, {});
  }

  /** A proposal only: nothing is created until a person approves it. */
  proposeCollection(name: string, itemIds: string[]) {
    return this.http.post<ProposeResult>('/api/collections/propose', { name, item_ids: itemIds });
  }

  ask(question: string) {
    return this.http.post<AskResult>('/api/ask', { question });
  }

  approvals() {
    return this.http.get<Proposal[]>('/api/approvals');
  }

  propose(file: File, title: string, category: string) {
    return this.http.post<ProposeResult>('/api/uploads/propose', {
      filename: file.name,
      content_type: file.type || 'application/octet-stream',
      size_bytes: file.size,
      title,
      category,
    });
  }

  uploadBlob(proposalId: string, file: File) {
    return this.http.post(`/api/uploads/${proposalId}/blob`, file, {
      headers: { 'Content-Type': file.type || 'application/octet-stream' },
    });
  }

  approve(id: string) {
    return this.http.post<{ status: string; record: Item }>(`/api/approvals/${id}/approve`, {});
  }

  edit(id: string, payload: Partial<Proposal['payload']>) {
    return this.http.post<{ status: string; hash: string; payload: Proposal['payload'] }>(
      `/api/approvals/${id}/edit`, { payload });
  }

  reject(id: string) {
    return this.http.post(`/api/approvals/${id}/reject`, {});
  }
}
