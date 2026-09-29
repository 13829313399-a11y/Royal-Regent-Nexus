import { createCanvas } from 'canvas';
import { PDFDocument } from 'pdf-lib';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  buildResultsPdf,
  collectPdfResults,
  pdfResultImages,
} from '../../apps/web/src/features/export/resultsPdf';
import { loadMergedResult } from '../../apps/web/src/features/patch/regionPatch';

vi.mock('../../apps/web/src/features/patch/regionPatch', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../apps/web/src/features/patch/regionPatch')>(),
  loadMergedResult: vi.fn(async () => null),
}));

function source(id: string) {
  return { id, file: new File(['source'], `${id}.png`), width: 80, height: 40 };
}

function imageBlob(width: number, height: number, jpeg = false): Blob {
  const canvas = createCanvas(width, height);
  const context = canvas.getContext('2d');
  context.fillStyle = jpeg ? '#2255aa' : '#aa5522';
  context.fillRect(0, 0, width, height);
  return new Blob([new Uint8Array(jpeg ? canvas.toBuffer('image/jpeg') : canvas.toBuffer('image/png'))]);
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.mocked(loadMergedResult).mockReset().mockResolvedValue(null);
});

describe('PDF summary export', () => {
  it('keeps queue order and excludes unfinished jobs and patch crops', () => {
    const blob = imageBlob(80, 40);
    const images = ['second', 'failed', 'patch', 'first', 'queued', 'missing'].map(source);
    const selected = pdfResultImages(images, {
      second: { status: 'done', resultUrl: 'blob:second' },
      first: { status: 'done', resultBlob: blob },
      failed: { status: 'failed', resultBlob: blob },
      patch: { status: 'done', resultBlob: blob },
      queued: { status: 'queued' },
      missing: { status: 'done' },
    }, [{ name: 'patch.png', parentId: 'first', rect: { x: 0, y: 0, width: 10, height: 10 }, createdAt: 1 }]);
    expect(selected.map((image) => image.id)).toEqual(['second', 'first']);
  });

  it('prefers saved merged results and otherwise uses the completed result', async () => {
    const original = imageBlob(80, 40);
    const merged = imageBlob(120, 60);
    vi.mocked(loadMergedResult).mockResolvedValueOnce(merged);
    const pages = await collectPdfResults([source('first'), source('second')], {
      first: { status: 'done', resultBlob: original },
      second: { status: 'done', resultBlob: original },
    });
    expect(pages.map((page) => page.name)).toEqual(['first.png', 'second.png']);
    expect(pages[0].blob).toBe(merged);
    expect(pages[1].blob).toBe(original);
  });

  it('exports recovered completed jobs directly from their stored history result', async () => {
    const images = [source('recovered')];
    const jobs = { recovered: { status: 'done' as const, historyResult: { batchId: 'batch-a', itemId: 'recovered' } } };
    const loadHistory = vi.fn(async () => imageBlob(500, 800));
    expect(pdfResultImages(images, jobs, [])).toEqual(images);
    const pages = await collectPdfResults(images, jobs, undefined, loadHistory);
    expect(loadHistory).toHaveBeenCalledWith({ batchId: 'batch-a', itemId: 'recovered' });
    const pdf = await PDFDocument.load(await (await buildResultsPdf(pages)).arrayBuffer());
    expect(pdf.getPage(0).getSize()).toEqual({ width: 375, height: 600 });
  });

  it('uses an unsaved live merge and also supports URL-only results', async () => {
    const fetchMock = vi.fn(async () => new Response(imageBlob(120, 60)));
    vi.stubGlobal('fetch', fetchMock);
    const pages = await collectPdfResults([source('first'), source('second')], {
      first: { status: 'done', resultBlob: imageBlob(80, 40) },
      second: { status: 'done', resultUrl: 'blob:second-result' },
    }, { imageId: 'first', url: 'blob:unsaved-merge' });
    expect(fetchMock.mock.calls).toEqual([['blob:unsaved-merge'], ['blob:second-result']]);
    const pdf = await PDFDocument.load(await (await buildResultsPdf(pages)).arrayBuffer());
    expect(pdf.getPages().map((page) => page.getSize())).toEqual([
      { width: 90, height: 45 }, { width: 90, height: 45 },
    ]);
  });

  it('creates exactly one page per PNG/JPEG in order, using actual result dimensions', async () => {
    const progress = vi.fn();
    const blob = await buildResultsPdf([
      { name: '横图.png', blob: imageBlob(80, 40) },
      { name: '竖图.jpg', blob: imageBlob(30, 90, true) },
    ], progress);
    expect(blob.type).toBe('application/pdf');
    const pdf = await PDFDocument.load(await blob.arrayBuffer());
    expect(pdf.getPages().map((page) => page.getSize())).toEqual([
      { width: 60, height: 30 }, { width: 22.5, height: 67.5 },
    ]);
    expect(progress.mock.calls).toEqual([[1, 2], [2, 2]]);
  });

  it('does not download an empty PDF or silently omit a corrupt page', async () => {
    await expect(buildResultsPdf([])).rejects.toThrow('没有可导出的结果');
    await expect(buildResultsPdf([
      { name: 'good.png', blob: imageBlob(80, 40) },
      { name: 'broken.png', blob: new Blob(['invalid']) },
    ])).rejects.toThrow('broken.png');
  });

  it('fails when a completed result URL is no longer readable', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status: 404 })));
    await expect(collectPdfResults([source('first')], {
      first: { status: 'done', resultUrl: 'blob:expired' },
    })).rejects.toThrow();
  });
});
