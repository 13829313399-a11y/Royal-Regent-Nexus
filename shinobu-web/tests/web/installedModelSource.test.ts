import { afterEach, expect, it, vi } from 'vitest';
import type { ModelPackageStore } from '../../apps/web/src/runtime/modelPackageStore';

vi.mock('../../apps/web/src/runtime/modelInstaller', () => ({
  inspectModelPackage: vi.fn(async () => ({ installed: true })),
}));

afterEach(() => { vi.unstubAllEnvs(); vi.restoreAllMocks(); vi.resetModules(); });

it('resolves upstream root-relative model and dictionary URLs from OPFS when hosted under rr', async () => {
  vi.stubEnv('BASE_URL', '/image-translation/');
  const { createInstalledModelAssetSource } = await import('../../apps/web/src/runtime/installedModelSource');
  const model = new Blob(['model']);
  const dictionary = new Blob(['text']);
  const store = {
    readAsset: vi.fn(async (_version: string, path: string) => path === 'detector.ort' ? model : dictionary),
  } as unknown as ModelPackageStore;
  const revoke = vi.spyOn(URL, 'revokeObjectURL');
  const resource = await createInstalledModelAssetSource(store, {
    schemaVersion: 1, version: 'test', assets: [
      { id: 'detector', path: 'detector.ort', size: model.size, sha256: '', url: '/image-translation/models/detector.ort' },
      { id: 'dictionary', path: 'paddleocr_v6_dict.txt', size: dictionary.size, sha256: '', url: '/image-translation/models/paddleocr_v6_dict.txt' },
    ],
  }, 'https://rr.test/image-translation/assets/pipeline.worker.js');
  const manifest = resource.source.manifestUrl();
  expect(manifest).toBe('https://rr.test/image-translation/models/models.json');
  const detector = resource.source.resolveAsset('/models/detector.ort', manifest);
  expect(detector).toMatch(/^blob:/);
  expect(resource.source.resolveAsset('/image-translation/models/detector.ort', manifest)).toBe(detector);
  expect(resource.source.resolveAsset('/models/paddleocr_v6_dict.txt', manifest)).toMatch(/^blob:/);
  resource.dispose();
  expect(revoke).toHaveBeenCalledTimes(2);
});
