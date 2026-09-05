import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { ConnectorWorker } from '../src/worker.mjs';
import { ConnectorClient } from '../src/client.mjs';
import { mergeReport, initialStatus } from '../src/bambu/status.mjs';

function fixture() {
  let now = 0, granted = false, failDispatch = false;
  const messages = [], adapters = [];
  const iso = milliseconds => new Date(milliseconds).toISOString();
  const client = { async post(path, payload) {
    messages.push([path, payload]);
    if (path === '/printers') return { printers: [{ printer_id: 'printer-1' }] };
    if (path === '/leases/acquire') {
      if (granted) return { acquired: false };
      granted = true;
      return { acquired: true, leased_until: iso(now + 30000), server_time: iso(now), port: 8883,
        leader_lease_id: 'leader-1', printer_id: 'printer-1', machine_no: 1, generation: 0, connection_revision: 1 };
    }
    if (path === '/commands/claim') return { server_time: iso(now), commands: [{ command_id: 'command-1',
      command_lease_id: 'command-lease', action: 'pause', leased_until: iso(now + 8000) }] };
    if (path === '/commands/dispatch') { if (failDispatch) throw new Error('lost_response'); return { send_permitted: false }; }
    if (path === '/leases/renew') return { server_time: iso(now), leased_until: iso(now + 30000), connection_revision: 2 };
    return {};
  } };
  const worker = new ConnectorWorker({ client, secretStore: {}, clock: () => now,
    adapterFactory: () => {
      const adapter = new EventEmitter();
      Object.assign(adapter, { ready: true, session: 'session-1', start() {}, stop() { this.closed = true },
        execute() { assert.fail('uncertain dispatch must never write MQTT') } });
      adapters.push(adapter); return adapter;
    } });
  const prepare = async () => {
    await worker.start(); clearInterval(worker.timer);
    adapters[0].emit('state', { connection_session_id: 'session-1', event_id: 'e1', sequence: 1,
      observed_at: iso(now), connected: true, state: 'RUNNING', progress_percent: 0, remaining_minutes: 0 });
    await worker.slots.get('printer-1').queue;
  };
  return { worker, prepare, messages, adapters, advance(value) { now += value }, failDispatch() { failDispatch = true } };
}

test('lost dispatch response and duplicate permission never cause a wire retry', async () => {
  const f = fixture(); await f.prepare();
  try {
    await f.worker.command(f.worker.slots.get('printer-1'));
    f.failDispatch();
    await assert.rejects(f.worker.command(f.worker.slots.get('printer-1')), /lost_response/);
    assert.equal(f.messages.filter(([path]) => path === '/commands/ack').length, 0);
  } finally { await f.worker.stop() }
});

test('expired local lease closes the socket and never renews a paused process grant', async () => {
  const f = fixture(); await f.prepare();
  try {
    f.advance(30000); await f.worker.tick();
    assert.equal(f.adapters[0].closed, true);
    assert.equal(f.messages.filter(([path]) => path === '/leases/renew').length, 0);
  } finally { await f.worker.stop() }
});

test('configuration revision changes retire a live adapter before more commands', async () => {
  const f = fixture(); await f.prepare();
  try {
    f.advance(9000); await f.worker.tick();
    assert.equal(f.adapters[0].closed, true);
  } finally { await f.worker.stop() }
});

test('service client forbids remote cleartext and credential redirects', async () => {
  assert.throws(() => new ConnectorClient({ baseUrl: 'http://192.168.1.2', token: 'test', instanceId: 'test' }));
  let options;
  const client = new ConnectorClient({ baseUrl: 'https://backend.example', token: 'test', instanceId: 'test',
    fetchImpl: async (_url, value) => { options = value; return { ok: false, status: 302 }; } });
  await assert.rejects(client.post('/heartbeat', { version: 'test' }), /connector_api_302/);
  assert.equal(options.redirect, 'error');
});

test('a new device job cannot inherit the prior job completion state', () => {
  const finished = mergeReport(initialStatus(), { subtask_id: 'old', gcode_state: 'FINISH', mc_percent: 100 }, 'now');
  const next = mergeReport(finished, { subtask_id: 'new', subtask_name: 'same-file' }, 'later');
  assert.equal(next.state, 'UNKNOWN'); assert.equal(next.progress_percent, 0);
});
