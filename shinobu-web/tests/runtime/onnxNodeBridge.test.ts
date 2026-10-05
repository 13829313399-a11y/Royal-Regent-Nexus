import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createSession, disposeAll } from '../../packages/model-runtime/src/runtime/onnxNodeBridge';

const { create, release } = vi.hoisted(() => ({ create: vi.fn(), release: vi.fn() }));
vi.mock('onnxruntime-node', () => ({ InferenceSession: { create } }));

describe('Node CPU session pools', () => {
  beforeEach(() => {
    create.mockReset(); release.mockReset();
    create.mockResolvedValue({ inputNames: ['image'], outputNames: ['text'], release });
  });
  afterEach(async () => { await disposeAll(); });

  it('keeps standalone provider defaults and reuses its session', async () => {
    const first = await createSession('ocr', '/ocr.onnx', ['cpu']);
    expect(await createSession('ocr', '/ocr.onnx', ['cpu'])).toEqual(first);
    expect(create).toHaveBeenCalledExactlyOnceWith('/ocr.onnx', { executionProviders: ['cpu'] });
  });

  it('bounds the CPU fallback without overriding CUDA options', async () => {
    create.mockRejectedValueOnce(new Error('CUDA unavailable'));
    const handle = await createSession('ocr', '/ocr.onnx', ['cuda'], undefined, 2);
    expect(handle.provider).toBe('cpu');
    expect(create).toHaveBeenNthCalledWith(1, '/ocr.onnx', { executionProviders: ['cuda'] });
    expect(create).toHaveBeenNthCalledWith(2, '/ocr.onnx', {
      executionProviders: ['cpu'], intraOpNumThreads: 2, interOpNumThreads: 1,
    });
  });

  it('keeps bounded pools separate from default pools and releases both', async () => {
    const defaultHandle = await createSession('ocr', '/ocr.onnx', ['cpu']);
    const bounded = await createSession('ocr', '/ocr.onnx', ['cpu'], undefined, 2);
    expect(bounded.sessionId).not.toBe(defaultHandle.sessionId);
    expect(await createSession('ocr', '/ocr.onnx', ['cpu'], undefined, 2)).toEqual(bounded);
    expect(create).toHaveBeenCalledTimes(2);
    await disposeAll(); expect(release).toHaveBeenCalledTimes(2);
  });

  it('rejects invalid thread counts before loading a model', async () => {
    for (const count of [0, -1, 1.5, NaN]) {
      await expect(createSession('ocr', '/ocr.onnx', ['cpu'], undefined, count)).rejects.toThrow('Invalid CPU thread count');
    }
    expect(create).not.toHaveBeenCalled();
  });
});
