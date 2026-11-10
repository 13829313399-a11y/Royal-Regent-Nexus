// @vitest-environment jsdom
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../apps/web/src/server/ServerApp';
import { canApplyJobPoll, jobStateLabel, jobStateTone, requestId, type Job } from '../../apps/web/src/server/api';

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
  it('does not describe a generated file with unverified content as fully completed',()=>{
    const result={...job('review',1),summary:{content_status:'needs_review',layout_status:'partial',pipeline:'document-layout-v2'}};
    expect(jobStateLabel(result)).toBe('译文需核对');expect(jobStateTone(result)).toBe('needs_review');
    expect(jobStateLabel({...result,summary:{...result.summary,content_status:'reviewed'}})).toContain('部分版式待核对');
  });
  it('shows a complete translation even when it was not placed in the original image',async()=>{
    vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);
    const result=job('complete',1);
    result.summary={content_status:'reviewed',layout_status:'partial',pipeline:'document-layout-v2'};
    result.artifacts.push({id:'review-complete',role:'translation_review',format:'json',filename:'translation-review.json',size:1},
      {id:'complete-text',role:'complete_text',format:'txt',filename:'完整译文与原文对照.txt',size:1});
    vi.stubGlobal('fetch',vi.fn(async(url:string)=>{
      let value:unknown;
      if(url.includes('/capabilities'))value={worker:{online:true},image_translation:{available:true},translation:{offline_available:true,online_available:true,online_model:'test-vision-model'},limits:{max_file_bytes:1000000,max_pages:200}};
      else if(url.includes('/jobs?'))value={items:[result],total:1};
      else if(url.includes('/sources/'))value={id:'complete',inspection_status:'succeeded',artifacts:[],manifest:{pages:[]}};
      else if(url.includes('/artifacts/review-complete/'))value={pages:[{page_index:0,width_pt:100,height_pt:100}],
        regions:[{id:'b1',source:'Do not pull too tight',translation:'不要拉得过紧',page_index:0,bbox_pt:[10,10,50,30],rendered:false,reason:'layout-space',translation_status:'translated'}],issues:['完整内容见对照译文']};
      else throw new Error('Unexpected API '+url);
      return new Response(JSON.stringify(value));
    }));
    const container=document.createElement('div');document.body.append(container);root=createRoot(container);
    await act(async()=>root!.render(React.createElement(App)));
    expect(document.body.textContent).toContain('页图、文字与术语发送至 test-vision-model');
    await click('我的历史');await act(async()=>(document.querySelector('.rs-history-row') as HTMLButtonElement).click());
    expect(Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='完整译文')?.getAttribute('aria-pressed')).toBe('true');
    await click('原位结果');
    await click('完整译文');
    expect(document.querySelector('.rs-complete-text')?.textContent).toContain('不要拉得过紧');
    expect(document.querySelector('.rs-complete-text')?.textContent).toContain('原位未回填');
    expect(document.querySelector('a[href*="complete-text/download"]')).toBeTruthy();
  });
  it('shows missing-text warnings outside the collapsed region list', async () => {
    vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
    const result=job('unread',1);
    result.artifacts.push({id:'review',role:'translation_review',format:'json',filename:'translation-review.json',size:1});
    vi.stubGlobal('fetch',vi.fn(async (url:string)=>{
      let value:unknown;
      if(url.includes('/capabilities'))value={worker:{online:true},image_translation:{available:true},
        translation:{offline_available:true,online_available:false},limits:{max_file_bytes:1_000_000,max_pages:200}};
      else if(url.includes('/jobs?'))value={items:[result],total:1};
      else if(url.includes('/sources/'))value={id:'unread',inspection_status:'succeeded',artifacts:[],manifest:{pages:[]}};
      else if(url.includes('/artifacts/review/'))value={pages:[],regions:[],issues:['该页未识别出可翻译文字，保留原图']};
      else throw new Error('Unexpected API: '+url);
      return new Response(JSON.stringify(value));
    }));
    const container=document.createElement('div');document.body.append(container);root=createRoot(container);
    await act(async()=>root!.render(React.createElement(App)));
    await click('我的历史');
    await act(async()=>(document.querySelector('.rs-history-row') as HTMLButtonElement).click());
    const notice=document.querySelector('.rs-review-notices');
    expect(notice?.textContent).toContain('该页未识别出可翻译文字');
    expect(notice?.closest('details')).toBeNull();
    expect(document.querySelector('.rs-review details')?.hasAttribute('open')).toBe(false);
    expect(document.querySelector('.rs-review summary')?.textContent).toContain('本页已识别文字核对');
    expect(document.querySelector('.rs-review-list')?.textContent).toContain('请对照原图检查');
  });

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
