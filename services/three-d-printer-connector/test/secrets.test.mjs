import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { FileSecretStore } from '../src/secrets.mjs';

test('file store loads explicit references, rejects traversal/oversize/extra fields without leaking values', t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'rr-3d-secret-test-'));
  t.after(() => {
    assert.equal(path.dirname(path.resolve(root)), path.resolve(os.tmpdir()));
    assert.ok(path.basename(root).startsWith('rr-3d-secret-test-'));
    fs.rmSync(root, { recursive: true });
  });
  const target = path.join(root, 'printer-01.json');
  const value = { serial: 'SIMULATED-SERIAL', access_code: 'test-access-code' };
  fs.writeFileSync(target, JSON.stringify(value), { mode: 0o600 });
  const store = new FileSecretStore(root);
  assert.deepEqual(store.get('printer-01'), value);
  for (const ref of ['../printer-01', 'printer-99', '/absolute-path'])
    assert.throws(() => store.get(ref), { message: 'device_secret_unavailable' });
  fs.writeFileSync(target, JSON.stringify({ ...value, unexpected: true }));
  assert.throws(() => store.get('printer-01'), { message: 'device_secret_unavailable' });
  fs.writeFileSync(target, 'x'.repeat(16385));
  assert.throws(() => store.get('printer-01'), { message: 'device_secret_unavailable' });
  if (process.platform !== 'win32') {
    fs.writeFileSync(target, JSON.stringify(value));
    fs.chmodSync(target, 0o644);
    assert.throws(() => store.get('printer-01'), { message: 'device_secret_unavailable' });
  }
});
