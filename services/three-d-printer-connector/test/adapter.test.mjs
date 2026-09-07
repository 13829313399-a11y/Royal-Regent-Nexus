import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { BambuAdapter } from '../src/bambu/BambuAdapter.mjs';
import { Decoder, mqttString, packet, publishBody, publishPacket } from '../src/bambu/mqtt.mjs';
import { initialStatus, mergeReport } from '../src/bambu/status.mjs';
import { simulator, fingerprint, until } from './simulator.mjs';

const config = (n = 1) => ({ factoryId: 'huakang-a', machineNo: n, host: `10.33.30.${100 + n}`,
  printerId: `printer-${n}`, credentialRef: `printer-${String(n).padStart(2, '0')}`,
  certificateFingerprint: fingerprint, controlVerified: true });
const secretStore = { get: () => ({ serial: 'TEST-SERIAL', access_code: 'test-access-code' }) };

async function setup(t, serverOptions = {}, options = {}, printerConfig = config()) {
  const server = await simulator(serverOptions);
  const adapter = new BambuAdapter(printerConfig, { secretStore, leaseValid: () => true,
    transport: server.transport, reconnectBaseMs: 30, reconnectMaxMs: 100, heartbeatMs: 1000,
    ...options });
  t.after(async () => { adapter.stop(); await server.close(); });
  return { server, adapter };
}
const command = (commandId = 'cmd-1', action = 'pause') => ({ commandId, action, leaseId: 'lease-1', valid: () => true, timeoutMs: 300 });
async function running(adapter, server) {
  adapter.start(); await until(() => adapter.ready);
  server.report({ gcode_state: 'RUNNING', subtask_name: 'test.3mf', subtask_id: 'job-1', mc_percent: 10 });
  await until(() => adapter.snapshot().state === 'RUNNING');
}

test('decoder handles split/coalesced frames and rejects oversized/malformed data', () => {
  const a = publishPacket('device/test/report', { print: { gcode_state: 'RUNNING' } });
  const decoder = new Decoder();
  assert.equal(decoder.push(a.subarray(0, 3)).length, 0);
  const frames = decoder.push(Buffer.concat([a.subarray(3), packet(0xd0)]));
  assert.equal(frames.length, 2);
  assert.equal(publishBody(frames[0]).topic, 'device/test/report');
  assert.throws(() => new Decoder().push(Buffer.from([0x30, 0xff, 0xff, 0xff, 0xff])), /limit|malformed/);
  assert.throws(() => publishBody({ header: 0x30, body: Buffer.from([0, 99]) }), /topic/);
  assert.throws(() => mqttString('x'.repeat(65536)), /limit/);
});

test('partial report preserves AMS/material, bounds values and leaves unproven job identity empty', () => {
  const first = mergeReport(initialStatus(), { gcode_state: 'PRINTING', subtask_name: 'file', mc_percent: 999,
    ams: { tray_now: 5, ams: [{ id: '1', tray: [{ id: '1', tray_type: 'PLA' }] }] } }, '2026-01-01T00:00:00Z');
  assert.equal(first.progress_percent, 100);
  assert.equal(first.live_material, 'PLA');
  assert.equal(first.device_job_key, '');
  const next = mergeReport(first, { nozzle_temper: 210 }, '2026-01-01T00:00:01Z');
  assert.equal(next.live_material, 'PLA');
  assert.equal(next.state, 'RUNNING');
  assert.throws(() => mergeReport(first, { mc_percent: 'NaN' }, ''), /number/);
  assert.equal(mergeReport(first, { gcode_state: 'FIRMWARE_NEW_STATE' }, '').state, 'UNKNOWN');
});

test('refuses public destinations, inline secrets and missing leader before opening sockets', () => {
  assert.throws(() => new BambuAdapter({ ...config(), host: '8.8.8.8' }), /config/);
  assert.throws(() => new BambuAdapter({ ...config(), accessCode: 'test-access-code' }), /config/);
  const adapter = new BambuAdapter(config(), { transport: () => assert.fail('must not connect') });
  assert.throws(() => adapter.start(), /lease/);
});

test('certificate mismatch sends no credentials or MQTT CONNECT', async t => {
  const { adapter, server } = await setup(t, {}, { secretStore: { get: () => assert.fail('must not load secret') } },
    { ...config(), certificateFingerprint: '0'.repeat(64) });
  const event = once(adapter, 'state'); adapter.start();
  assert.equal((await event)[0].reason, 'certificate_mismatch');
  assert.equal(server.stats.connects, 0);
});

for (const [name, serverOptions] of [['authentication', { connack: 5 }], ['subscription', { suback: 128 }]]) {
  test(`rejects MQTT ${name} failure without readiness/control`, async t => {
    const { adapter, server } = await setup(t, serverOptions);
    const event = once(adapter, 'state'); adapter.start();
    assert.match((await event)[0].reason, /rejected/);
    assert.equal(adapter.ready, false);
    assert.equal(server.commands.length, 0);
  });
}

test('fragmented live events keep timestamps, command waits for evidence and retry sends once', async t => {
  const { adapter, server } = await setup(t, { fragment: true });
  await running(adapter, server);
  const observed = adapter.snapshot().observed_at;
  assert.equal(adapter.snapshot().observed_at, observed);
  const first = adapter.execute(command());
  assert.equal(adapter.execute(command()), first);
  assert.throws(() => adapter.execute({ ...command(), action: 'resume' }), /conflict/);
  const result = await first;
  assert.equal(result.status, 'succeeded');
  assert.equal(result.evidence.state, 'PAUSE');
  assert.equal(server.commands.length, 1);
  assert.match(server.commands[0].sequence_id, /^\d+$/);
  assert.equal(adapter.execute(command()), first);
  assert.equal(JSON.stringify(result).includes('TEST-SERIAL'), false);
  assert.equal(JSON.stringify(result).includes('test-access-code'), false);
  const resumed = await adapter.execute(command('cmd-2', 'resume'));
  assert.equal(resumed.status, 'succeeded');
  assert.notEqual(server.commands[0].sequence_id, server.commands[1].sequence_id);
});

test('retained state cannot enable or acknowledge control; absent evidence is unknown', async t => {
  const { adapter, server } = await setup(t, { acknowledge: false });
  adapter.start(); await until(() => adapter.ready);
  server.report({ gcode_state: 'RUNNING' }, { retained: true });
  await new Promise(resolve => setTimeout(resolve, 30));
  assert.equal(adapter.snapshot().state, 'STALE');
  assert.throws(() => adapter.execute(command()), /permitted/);
  server.report({ gcode_state: 'RUNNING' }); await until(() => adapter.snapshot().state === 'RUNNING');
  const result = adapter.execute(command());
  server.report({ gcode_state: 'PAUSE' }, { retained: true });
  assert.equal((await result).status, 'unknown');
  assert.equal(server.commands.length, 1);
});

test('expired status and unverified firmware capability prevent control', async t => {
  let now = Date.now();
  const { adapter, server } = await setup(t, {}, { clock: () => now });
  await running(adapter, server);
  const observed = adapter.snapshot().observed_at;
  now += 31000;
  assert.equal(adapter.snapshot().state, 'STALE');
  assert.equal(adapter.snapshot().observed_at, observed);
  assert.throws(() => adapter.execute(command()), /permitted/);
  now -= 31000;
  const readonly = new BambuAdapter({ ...config(), controlVerified: false });
  assert.throws(() => readonly.execute(command()), /permitted/);
});

test('unknown firmware report downgrades control, ignores other topics', async t => {
  const { adapter, server } = await setup(t);
  await running(adapter, server);
  server.report({ gcode_state: 'NEW_FIRMWARE_STATE' });
  await until(() => adapter.snapshot().state === 'UNKNOWN');
  server.report({ gcode_state: 'RUNNING' });
  await until(() => adapter.snapshot().state === 'RUNNING');
  assert.throws(() => adapter.execute(command()), /permitted/);
  const broken = once(adapter, 'state');
  server.report({ gcode_state: 'FINISH' }, { topic: 'device/other/report' });
  assert.equal((await broken)[0].reason, 'protocol_error');
});

test('lease loss closes connection and makes pending/late command evidence unknown', async t => {
  let owns = true;
  const { adapter, server } = await setup(t, { acknowledge: false }, { leaseValid: () => owns, leaseCheckMs: 10 });
  await running(adapter, server);
  const result = adapter.execute(command());
  owns = false;
  await until(() => adapter.stopped);
  assert.equal((await result).reason, 'lease_lost');
  await until(() => server.stats.active === 0);
  assert.throws(() => adapter.execute(command('new-command')), /permitted/);
});

test('lost command lease refuses a matching subsequent state as success', async t => {
  let commandLease = true;
  const { adapter, server } = await setup(t, { acknowledge: false });
  await running(adapter, server);
  const result = adapter.execute({ ...command(), valid: () => commandLease });
  commandLease = false;
  server.report({ gcode_state: 'PAUSE' });
  assert.equal((await result).reason, 'lease_lost');
});

test('disconnect/reconnect changes session, requests full status and never fabricates finish', async t => {
  const { adapter, server } = await setup(t);
  const events = []; adapter.on('state', event => events.push(event));
  await running(adapter, server);
  const oldSession = adapter.session;
  server.outage();
  await until(() => adapter.session !== oldSession && adapter.ready);
  assert.equal(adapter.snapshot().state, 'STALE');
  server.report({ gcode_state: 'RUNNING', subtask_id: 'job-1' });
  await until(() => adapter.snapshot().state === 'RUNNING');
  assert.equal(events.some(event => event.state === 'FINISH'), false);
  assert.ok(server.requests.filter(value => value.pushing?.command === 'pushall').length >= 2);
  for (const session of new Set(events.map(event => event.connection_session_id))) {
    const sequences = events.filter(event => event.connection_session_id === session).map(event => event.sequence);
    assert.deepEqual(sequences, [...new Set(sequences)].sort((a, b) => a - b));
  }
});

test('11 independent simulated printers connect and recover without duplicate local sessions', async t => {
  const pairs = await Promise.all(Array.from({ length: 11 }, (_, n) => setup(t, {}, {}, config(n + 1))));
  await Promise.all(pairs.map(({ adapter, server }) => running(adapter, server)));
  assert.equal(pairs.filter(({ adapter }) => adapter.snapshot().state === 'RUNNING').length, 11);
  const sessions = pairs.map(({ adapter }) => adapter.session);
  for (const { server } of pairs) server.outage();
  await until(() => pairs.every(({ adapter }, n) => adapter.session !== sessions[n] && adapter.ready));
  for (const { server } of pairs) server.report({ gcode_state: 'RUNNING', subtask_id: 'job-1' });
  await until(() => pairs.every(({ adapter }) => adapter.snapshot().state === 'RUNNING'));
  assert.ok(pairs.every(({ server }) => server.stats.maxActive === 1));
});
