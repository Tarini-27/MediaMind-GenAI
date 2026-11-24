import { Component, OnInit, inject, signal } from '@angular/core';
import { Approvals } from './components/approvals';
import { Detail } from './components/detail';
import { Header } from './components/header';
import { Login } from './components/login';
import { Results } from './components/results';
import { Sidebar } from './components/sidebar';
import { Upload } from './components/upload';
import { Store } from './core/store.service';

/** Three panes, as in the proposal's sample screen: collections · chat and results · selected item. */
@Component({
  selector: 'app-root',
  imports: [Header, Sidebar, Results, Detail, Approvals, Upload, Login],
  template: `
    @if (store.session.me() === null) {
      <mm-login />
    } @else if (store.session.me()) {
    <mm-header (upload)="uploadOpen.set(true)" />
    <div class="shell">
      <mm-sidebar (approvals)="approvalsOpen.set(true)" />
      <mm-results />
      <mm-detail />
    </div>
    <mm-approvals [open]="approvalsOpen()" (closed)="approvalsOpen.set(false)" />
    <mm-upload [open]="uploadOpen()" (closed)="uploadOpen.set(false)" />
    }
    @if (store.toast(); as t) { <div class="toast" role="status">{{ t }}</div> }`,
  styles: `
    :host { display: flex; flex-direction: column; height: 100vh; }
    .shell { flex: 1; min-height: 0; display: grid; grid-template-columns: 220px minmax(0, 1fr) 400px; }
    @media (max-width: 1100px) { .shell { grid-template-columns: 220px minmax(0, 1fr); } }
    @media (max-width: 720px) { .shell { grid-template-columns: 1fr; grid-template-rows: auto 1fr; } }
    .toast { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); background: var(--text); color: var(--bg);
      padding: 10px 18px; border-radius: 10px; z-index: 40; font-size: 14px; }`,
})
export class App implements OnInit {
  store = inject(Store);
  approvalsOpen = signal(false);
  uploadOpen = signal(false);
  ngOnInit() { this.store.init(); }
}
