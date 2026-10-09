// @vitest-environment jsdom
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../apps/web/src/server/ServerApp';
import { canApplyJobPoll, requestId, type Job } from '../../apps/web/src/server/api';

let root: Root | undefined;
afterEach(async () => {
  if (root) await act(async () => root!.unmount());
  root = undefined;
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
});
function job(id: string, pages: number): Job {
  return { id, source_id: id, source_name: id + '.pdf', operation: 'image_translate', execution_status: 'succeeded',
    stage: 'validate', completed_units: 1, total_units: 1, revision: 1, options: {}, created_at: '2026-09-29T00:00:00Z',
    artifacts: Array.from({ length: pages }, (_, i) => ({ id: id + '-' + i, role: 'result_page', format: 'png', filename: `page-000${i + 1}.png`, size: 1 })) };
}
async function click(text: string) {
  const button = Array.from(document.querySelectorAll('button')).find(element => element.textContent === text);
  expect(button).toBeTruthy();
  await act(async () => button!.click());
}

describe('server translation workbench', () => {
  it('switches from the second PDF page to a one-page image without stale page crashes', async () => {
    vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
    const jobs = [job('multi', 2), job('single', 1)];
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      let value: unknown;
      if (url.includes('/capabilities')) value = { worker: { online: true }, image_translation: { available: true },
        translation: { offline_available: true, online_available: false }, limits: { max_file_bytes: 1_000_000, max_pages: 200 } };
      else if (url.includes('/jobs?')) value = { items: jobs, total: jobs.length };
      else if (url.includes('/sources/')) value = { id: url.split('/').pop(), inspection_status: 'succeeded', artifacts: [],
        manifest: { pages: [{ page_index: 0, width_pt: 300, height_pt: 200,
          image_resize: url.endsWith('/single') ? { original_size: [6000, 4000], processing_size: [300, 200] } : undefined },
          { page_index: 1, width_pt: 300, height_pt: 200 }] } };
      else throw new Error('Unexpected API: ' + url);
      return new Response(JSON.stringify(value));
    }));
    const container = document.createElement('div'); document.body.append(container);
    root = createRoot(container);
    await act(async () => root!.render(React.createElement(App)));
    await click('我的历史');
    await act(async () => (document.querySelector('.rs-history-row') as HTMLButtonElement).click());
    await click('下一页');
    expect(document.querySelector('.rs-pagination')?.textContent).toContain('2 / 2');
    await click('我的历史');
    await act(async () => (document.querySelectorAll('.rs-history-row')[1] as HTMLButtonElement).click());
    expect(document.querySelector('.rs-pagination')?.textContent).toContain('1 / 1');
    expect(document.querySelector('.rs-image-wrap img')?.getAttribute('src')).toContain('single-0');
    expect(document.body.textContent).toContain('高分辨率图片已自动缩小：6000 × 4000 → 300 × 200 像素，原文件保留。');
    expect(document.body.textContent).not.toContain('API Key');
    expect(document.body.textContent).not.toContain('导入模型');
  });

  it('creates unique request IDs without crypto.randomUUID on ordinary HTTP', () => {
    expect(requestId()).toMatch(/^[0-9a-f]{32}$/);
    expect(new Set(Array.from({ length: 100 }, requestId)).size).toBe(100);
  });

  it('ignores delayed running snapshots after cancellation or replacement by retry', () => {
    const running = { ...job('old', 1), execution_status: 'running' };
    const cancelled = { ...running, execution_status: 'cancelled' };
    const retry = { ...running, id: 'retry', execution_status: 'queued' };
    expect(canApplyJobPoll(cancelled, running)).toBe(false);
    expect(canApplyJobPoll(retry, running)).toBe(false);
    expect(canApplyJobPoll(retry, { ...retry, execution_status: 'succeeded' })).toBe(true);
    expect(canApplyJobPoll(undefined, running)).toBe(false);
  });
});
