import type { ImportedImage } from '../import/imageImporter';
import type { QueueJobState } from '../workbench/webWorkbench';
import {
  loadMergedResult,
  mergedStorageKey,
  resultBlobForPatch,
  type PatchRecord,
} from '../patch/regionPatch';

export type PdfSourceImage = Pick<ImportedImage, 'id' | 'width' | 'height'> & {
  file: Pick<File, 'name' | 'size'>;
};
export type ResultPdfPage = { name: string; blob: Blob };

export function pdfResultImages(
  images: readonly PdfSourceImage[],
  jobs: Readonly<Record<string, QueueJobState>>,
  patches: readonly PatchRecord[],
): PdfSourceImage[] {
  const patchNames = new Set(patches.map((patch) => patch.name));
  return images.filter((image) => (
    !patchNames.has(image.file.name)
    && jobs[image.id]?.status === 'done'
    && Boolean(jobs[image.id].resultBlob || jobs[image.id].resultUrl || jobs[image.id].historyResult)
  ));
}

/** Capture the results before building the PDF, including unsaved merge previews. */
export async function collectPdfResults(
  images: readonly PdfSourceImage[],
  jobs: Readonly<Record<string, QueueJobState>>,
  liveMerged?: { imageId: string; url: string },
  loadHistoryResult?: (reference: NonNullable<QueueJobState['historyResult']>) => Promise<Blob>,
): Promise<ResultPdfPage[]> {
  return Promise.all(images.map(async (image) => {
    // Start reading object URLs immediately, before selection changes can revoke them.
    const job = jobs[image.id];
    const result = job?.historyResult && !job.resultBlob && !job.resultUrl && loadHistoryResult
      ? loadHistoryResult(job.historyResult)
      : resultBlobForPatch(job);
    const merged = liveMerged?.imageId === image.id
      ? resultBlobForPatch({ resultUrl: liveMerged.url })
      : loadMergedResult(mergedStorageKey({
        name: image.file.name,
        size: image.file.size,
        width: image.width,
        height: image.height,
      }));
    const [resultBlob, mergedBlob] = await Promise.all([result, merged]);
    const blob = mergedBlob ?? resultBlob;
    if (!blob) throw new Error(image.file.name);
    return { name: image.file.name, blob };
  }));
}

/** One full-resolution result per page, with no cropping or extra JPEG compression. */
export async function buildResultsPdf(
  pages: readonly ResultPdfPage[],
  onProgress?: (completed: number, total: number) => void,
): Promise<Blob> {
  if (pages.length === 0) throw new Error('没有可导出的结果');
  const { PDFDocument } = await import('pdf-lib');
  const pdf = await PDFDocument.create();
  pdf.setCreator('ShinobuTranslator');
  for (const [index, source] of pages.entries()) {
    try {
      const bytes = new Uint8Array(await source.blob.arrayBuffer());
      const image = bytes[0] === 0xff && bytes[1] === 0xd8
        ? await pdf.embedJpg(bytes)
        : await pdf.embedPng(bytes);
      // Match the usual 96 DPI image display size; embedded pixels stay unchanged.
      const width = image.width * 0.75;
      const height = image.height * 0.75;
      const page = pdf.addPage([width, height]);
      page.drawImage(image, { x: 0, y: 0, width, height });
      await pdf.flush();
    } catch (error) {
      throw new Error(source.name, { cause: error });
    }
    onProgress?.(index + 1, pages.length);
    // Give the browser a chance to paint progress between large images.
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
  }
  const bytes = await pdf.save();
  return new Blob([new Uint8Array(bytes)], { type: 'application/pdf' });
}
