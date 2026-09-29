import React from 'react';
import ReactDOM from 'react-dom/client';
import { installTrustedTypesPolicy } from './runtime/trustedTypes';
import { isRrIntegration, prepareRrSession, rrToolsUrl, watchRrSession } from './runtime/rrIntegration';
import './styles.css';
import { isGitHubPagesBuild } from './runtime/localModelImport';
import { preparePagesIsolation } from './runtime/pagesIsolation';

installTrustedTypesPolicy();

async function start(): Promise<void> {
  if (!await prepareRrSession()) return;
  if (isGitHubPagesBuild && !await preparePagesIsolation()) return;
  const { App } = await import('./App');
  const root = ReactDOM.createRoot(document.getElementById('root')!);
  root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
  watchRrSession(() => root.unmount());
}
void start().catch(error => {
  const root = document.getElementById('root')!;
  const message = document.createElement('p');
  message.textContent = error instanceof Error ? error.message : String(error);
  root.replaceChildren(message);
  if (isRrIntegration) {
    const back = document.createElement('a');
    back.href = rrToolsUrl();
    back.textContent = '返回公共工具栏';
    root.append(back);
  }
});
