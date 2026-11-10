import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { createServer } from 'node:http';
import { ConnectorWorker } from '../src/worker.mjs';
import { ConnectorClient } from '../src/client.mjs';
import { mergeReport, initialStatus } from '../src/bambu/status.mjs';

function fixture({ controlVerified = true } = {}) {
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
        leader_lease_id: 'leader-1', printer_id: 'printer-1', machine_no: 1, generation: 0, connection_revision: 1,
        control_verified: controlVerified };
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

test('observation-only grants upload telemetry and renew without polling hardware commands', async () => {
  const f = fixture({ controlVerified: false }); await f.prepare();
  const originalPost = f.worker.client.post;
  f.worker.client.post = async (path, payload) => {
    const result = await originalPost(path, payload);
    return path === '/leases/renew' ? { ...result, connection_revision: 1 } : result;
  };
  try {
    f.advance(1000); await f.worker.tick();
    f.advance(8000); await f.worker.tick();
    assert.equal(f.messages.filter(([path]) => path === '/commands/claim').length, 0);
    assert.equal(f.messages.filter(([path]) => path === '/events').length, 1);
    assert.equal(f.messages.filter(([path]) => path === '/leases/renew').length, 1);
    assert.equal(f.adapters[0].closed, undefined);
  } finally { await f.worker.stop() }
});

test('a slow observer upload keeps its MQTT session and commits the original device frame once', async () => {
  const f = fixture({ controlVerified: false });
  await f.prepare();
  const received = [];
  const server = createServer(async (req, res) => {
    let body = '';
    for await (const chunk of req) body += chunk;
    received.push(JSON.parse(body));
    setTimeout(() => res.end('{"accepted":true}'), 2750);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const http = new ConnectorClient({ baseUrl: 'http://127.0.0.1:' + server.address().port,
    token: 'test', instanceId: 'test-observer' });
  const originalPost = f.worker.client.post;
  f.worker.client.post = (path, payload, timeout) => path === '/events'
    ? http.post(path, payload, timeout) : originalPost(path, payload);
  try {
    const slot = f.worker.slots.get('printer-1');
    f.adapters[0].emit('state', { connection_session_id: 'session-1', event_id: 'slow-original', sequence: 2,
      observed_at: '2026-11-10T03:30:00.000Z', connected: true, state: 'RUNNING', progress_percent: 45 });
    await slot.queue;
    assert.equal(received.length, 1);
    assert.equal(received[0].event_id, 'slow-original');
    assert.equal(received[0].observed_at, '2026-11-10T03:30:00.000Z');
    assert.equal(received[0].progress_percent, 45);
    assert.equal(f.adapters[0].closed, undefined);
  } finally {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
    await f.worker.stop();
  }
});

test('observer bursts leave room for lease renewal and skip an expired queued grant', async () => {
  const f = fixture({ controlVerified: false });
  await f.prepare();
  const originalPost = f.worker.client.post;
  const started = [], pending = [], renewals = [];
  f.worker.client.post = async (path, payload, timeout) => {
    if (path === '/events') {
      started.push(payload.event_id);
      await new Promise(resolve => pending.push(resolve));
    } else if (path === '/leases/renew') {
      renewals.push(timeout);
      return { server_time: new Date(9000).toISOString(), leased_until: new Date(39000).toISOString(), connection_revision: 1 };
    } else return originalPost(path, payload);
  };
  const done = Array.from({ length: 18 }, (_, i) => f.worker.uploadEvent(
    { controlVerified: false, closed: false, deadline: i === 4 ? 8000 : 27000 }, { event_id: i }));
  try {
    assert.deepEqual(started, [0, 1, 2, 3]);
    f.advance(9000);
    await f.worker.tick();
    assert.deepEqual(renewals, [8000]);
    while (pending.length) {
      pending.shift()();
      await new Promise(resolve => setImmediate(resolve));
      assert.ok(pending.length <= 4);
    }
    await Promise.all(done);
    assert.deepEqual(started, Array.from({ length: 18 }, (_, i) => i).filter(i => i !== 4));
    assert.equal(f.worker.observerUploads, 0);
  } finally { await f.worker.stop(); }
});

test('a lost upload response reuses identical evidence within the remaining lease budget', async () => {
  const f = fixture({ controlVerified: false });
  await f.prepare();
  const originalPost = f.worker.client.post, attempts = [];
  f.worker.client.post = async (path, payload, timeout) => {
    if (path !== '/events') return originalPost(path, payload);
    attempts.push({ payload, timeout });
    if (attempts.length === 1) { f.advance(500); throw new Error('lost_response'); }
  };
  try {
    const slot = f.worker.slots.get('printer-1');
    f.advance(25000);
    const payload = { event_id: 'unchanged', sequence: 2, observed_at: '2026-11-10T03:30:00.000Z' };
    await f.worker.uploadEvent(slot, payload);
    assert.deepEqual(attempts.map(a => a.timeout), [2000, 1500]);
    assert.strictEqual(attempts[0].payload, attempts[1].payload);
    assert.equal(f.worker.observationTimeout({ ...slot, controlVerified: true }), undefined);
    f.advance(1600);
    await f.worker.uploadEvent(slot, payload);
    assert.equal(attempts.length, 2);
  } finally { await f.worker.stop(); }
});

test('all eighteen observers acquire, report and renew while retaining physical identities', async () => {
  let now = 0;
  const messages = [], adapters = new Map();
  // Old 6-11 move to 9-14; credential references remain attached to each device.
  const numbers = [1, 2, 3, 4, 5, 9, 10, 11, 12, 13, 14, 6, 7, 8, 15, 16, 17, 18];
  const devices = numbers.map((machineNo, i) => ({ printerId: `physical-${i + 1}`,
    machineNo, credentialRef: `printer-${String(i + 1).padStart(2, '0')}` }));
  const iso = value => new Date(value).toISOString();
  const client = { async post(path, payload) {
    messages.push([path, payload]);
    if (path === '/printers') return { printers: devices.map(d => ({ printer_id: d.printerId })) };
    if (path === '/leases/acquire' || path === '/leases/renew') {
      const device = devices.find(d => d.printerId === payload.printer_id);
      assert.ok(device);
      return { acquired: true, server_time: iso(now), leased_until: iso(now + 30000),
        port: 8883, leader_lease_id: `lease-${device.printerId}`, machine_no: device.machineNo,
        credential_ref: device.credentialRef, connection_revision: 1, control_verified: false };
    }
    assert.notEqual(path, '/commands/claim');
    return {};
  } };
  const worker = new ConnectorWorker({ client, secretStore: {}, clock: () => now,
    adapterFactory: config => {
      const device = devices.find(d => d.printerId === config.printerId);
      assert.equal(config.machineNo, device.machineNo);
      assert.equal(config.credentialRef, device.credentialRef);
      const adapter = new EventEmitter();
      Object.assign(adapter, { ready: true, start() {}, stop() { this.closed = true; },
        execute() { assert.fail('observers must never control a printer'); } });
      adapters.set(config.printerId, adapter); return adapter;
    } });
  try {
    await worker.start(); clearInterval(worker.timer);
    assert.equal(adapters.size, 3);
    for (let batch = 1; batch < 6; batch++) {
      await worker.tick();
      assert.equal(adapters.size, (batch + 1) * 3);
    }
    assert.equal(adapters.size, 18);
    for (const device of devices) {
      adapters.get(device.printerId).emit('state', { connection_session_id: `session-${device.printerId}`,
        event_id: `event-${device.printerId}`, sequence: 1, observed_at: iso(now),
        connected: true, state: device.machineNo === 2 ? 'PAUSE' : 'RUNNING',
        progress_percent: 42, remaining_minutes: 12 });
    }
    await Promise.all([...worker.slots.values()].map(slot => slot.queue));
    now = 9000; await worker.tick();
    assert.equal(messages.filter(([path]) => path === '/leases/renew').length, 18);
    const events = messages.filter(([path]) => path === '/events').map(([, body]) => body);
    assert.deepEqual(new Set(events.map(e => e.printer_id)), new Set(devices.map(d => d.printerId)));
    assert.equal(events.find(e => e.printer_id === 'physical-2').state, 'PAUSE');
    assert.equal(messages.filter(([path]) => path.startsWith('/commands/')).length, 0);
    assert.ok([...adapters.values()].every(a => !a.closed));
  } finally { await worker.stop(); }
  assert.ok([...adapters.values()].every(a => a.closed));
});

test('shared API outage closes leases immediately then backs off and recovers with sanitized diagnostics', async () => {
  const f = fixture(); await f.prepare();
  const logs = []; f.worker.log = entry => logs.push(entry);
  const originalPost = f.worker.client.post;
  let fail = true, calls = 0;
  f.worker.client.post = async (path, payload) => {
    if (path === '/heartbeat') {
      calls++;
      if (fail) throw new Error('private-token http://private-host upstream secret body');
    }
    return originalPost(path, payload);
  };
  try {
    f.advance(10000); await f.worker.tick();
    assert.equal(f.adapters[0].closed, true);
    f.advance(500); await f.worker.tick(); assert.equal(calls, 1);
    f.advance(500); await f.worker.tick(); assert.equal(calls, 2);
    f.advance(1000); await f.worker.tick(); assert.equal(calls, 2);
    fail = false;
    f.advance(1000); await f.worker.tick(); assert.equal(calls, 3);
    assert.equal(f.worker.apiFailures, 0);
    assert.ok(logs.some(entry => entry.code === 'connector_api_recovered'));
    assert.deepEqual(logs.filter(entry => entry.retry_ms).map(entry => entry.retry_ms), [1000, 2000]);
    assert.doesNotMatch(JSON.stringify(logs), /private-token|private-host|secret body/);
  } finally { await f.worker.stop() }
});

test('device diagnostics distinguish transport failure and recovery while rate limiting unchanged failures', async () => {
  const f = fixture(); await f.prepare();
  const logs = []; f.worker.log = entry => logs.push(entry);
  const slot = f.worker.slots.get('printer-1');
  const emit = async event => {
    f.adapters[0].emit('state', { connection_session_id: 'session-1', event_id: 'test-event',
      sequence: 2, progress_percent: 0, remaining_minutes: 0, ...event });
    await slot.queue;
  };
  try {
    await emit({ connected: false, state: 'STALE', reason: 'tcp_connect_timeout' });
    await emit({ connected: false, state: 'STALE', reason: 'tcp_connect_timeout' });
    assert.equal(logs.length, 1);
    assert.equal(logs[0].reason, 'tcp_connect_timeout');
    await emit({ connected: true, state: 'RUNNING', reason: 'device_report', current_file: 'private-product-name' });
    await emit({ connected: true, state: 'RUNNING', reason: 'device_report' });
    assert.equal(logs.length, 2);
    assert.equal(logs[1].code, 'printer_telemetry_recovered');
    await emit({ connected: false, state: 'STALE', reason: 'private-access-code' });
    assert.equal(logs[2].reason, 'device_state');
    assert.doesNotMatch(JSON.stringify(logs), /private-product-name|private-access-code/);
  } finally { await f.worker.stop() }
});
