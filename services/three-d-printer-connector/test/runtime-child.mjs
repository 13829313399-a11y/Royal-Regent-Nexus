import tls from 'node:tls';
import { performance } from 'node:perf_hooks';
import { ConnectorClient } from '../src/client.mjs';
import { ConnectorWorker } from '../src/worker.mjs';
import { BambuAdapter } from '../src/bambu/BambuAdapter.mjs';

// IPC-only test harness, no production configuration or secret files are loaded.
let worker, timer, offset = 0;
process.on('message', async message => {
  try {
    if (message.type === 'start') {
      worker = new ConnectorWorker({
        client: new ConnectorClient({ baseUrl: process.env.THREE_D_TEST_API,
          instanceId: message.instance, token: process.env.THREE_D_TEST_TOKEN }),
        secretStore: { get: () => ({ serial: 'TEST-SERIAL', access_code: 'test-only' }) },
        clock: () => performance.now() + offset, pollMs: 500,
        adapterFactory: (config, options) => new BambuAdapter(config, { ...options,
          transport: value => tls.connect({ ...value, host: '127.0.0.1', port: message.ports[config.machineNo - 1] }),
          clock: () => Date.now() + offset, reconnectBaseMs: 30, reconnectMaxMs: 100, heartbeatMs: 1000 }),
      });
      await worker.start();
      timer = setInterval(() => process.send?.({ readyCount: [...worker.slots.values()].filter(s => s.adapter?.ready && !s.closed).length }), 100);
    } else if (message.type === 'advance') offset += message.milliseconds;
    else if (message.type === 'stop') {
      clearInterval(timer); await worker?.stop();
      process.send?.({ reply: message.id }); process.disconnect(); return;
    }
    process.send?.({ reply: message.id });
  } catch { process.send?.({ reply: message.id, error: 'child_failed' }); }
});
process.on('disconnect', async () => { clearInterval(timer); await worker?.stop(); });
