import React from 'react';
import { createRoot } from 'react-dom/client';
import { prepareRrSession, rrToolsUrl, watchRrSession } from '../runtime/rrIntegration';
import { installTrustedTypesPolicy } from '../runtime/trustedTypes';
import './server.css';

installTrustedTypesPolicy();
async function start() {
  if (!await prepareRrSession()) return;
  const { App } = await import('./ServerApp');
  const root = createRoot(document.getElementById('root')!);
  root.render(<React.StrictMode><App /></React.StrictMode>);
  watchRrSession(() => root.unmount());
}
void start().catch(error => {
  const message = document.createElement('p');
  message.textContent = error instanceof Error ? error.message : '暂时无法连接主站';
  const back = document.createElement('a');
  back.href = rrToolsUrl(); back.textContent = '返回公共工具栏';
  document.getElementById('root')!.replaceChildren(message, back);
});
