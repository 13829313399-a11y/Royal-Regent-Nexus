// Launched only by the isolated pytest API fixture. Never reads production env/config.
import assert from 'node:assert/strict';
import { performance } from 'node:perf_hooks';
import { fork } from 'node:child_process';
import { simulator, until } from './simulator.mjs';

const base = process.env.THREE_D_TEST_API;
assert.match(base, /^http:\/\/127\.0\.0\.1:\d+$/);
const servers = await Promise.all(Array.from({ length: 11 }, () => simulator()));
async function api(path, value) {
  const response = await fetch(base + path, { method: value ? 'POST' : 'GET',
    headers: { 'Content-Type': 'application/json', Cookie: process.env.THREE_D_TEST_COOKIE },
    body: value ? JSON.stringify(value) : undefined });
  assert.ok(response.ok, `${path}: ${response.status}`);
  return response.json();
}
const workers = ['runtime-a', 'runtime-b'].map(instance => {
  const child = fork(new URL('./runtime-child.mjs', import.meta.url), [], { windowsHide: true,
    stdio: ['ignore', 'ignore', 'pipe', 'ipc'] });
  let counter = 0, stopped = false;
  const pending = new Map();
  const result = { readyCount: 0, pid: child.pid,
    start: () => send({ type: 'start', instance, ports: servers.map(server => server.port) }),
    advance: () => send({ type: 'advance', milliseconds: 1800000 }),
    async stop() { if (stopped) return; stopped = true;
      try { await send({ type: 'stop' }); } finally { child.disconnect?.(); child.kill(); } },
  };
  child.on('message', message => {
    if (message.readyCount !== undefined) result.readyCount = message.readyCount;
    if (message.reply) { pending.get(message.reply)?.(message); pending.delete(message.reply); }
  });
  function send(message) {
    return new Promise((resolve, reject) => {
      const id = ++counter;
      const timeout = setTimeout(() => { pending.delete(id); reject(new Error('child_timeout')); }, 10000);
      pending.set(id, reply => { clearTimeout(timeout); reply.error ? reject(new Error(reply.error)) : resolve(reply); });
      child.send({ ...message, id });
    });
  }
  return result;
});

async function waitSnapshot(predicate, timeout = 10000) {
  const end = Date.now() + timeout;
  let snapshot;
  do {
    snapshot = await api('/_test/snapshot');
    if (predicate(snapshot)) return snapshot;
    await new Promise(resolve => setTimeout(resolve, 100));
  } while (Date.now() < end);
  assert.fail(JSON.stringify({ events: snapshot.events, printers: snapshot.printers,
    runs: snapshot.runs.map(r => [r.machine_no, r.run_status]), commands: snapshot.commands.map(c => c.status) }));
}

try {
  await api('/_test/configure', { fingerprint: servers[0].fingerprint });
  await Promise.all(workers.map(worker => worker.start()));
  assert.notEqual(workers[0].pid, workers[1].pid);
  await until(() => servers.every(server => server.stats.connects === 1 && server.requests.length), 10000);
  const started = performance.now();
  servers.forEach((server, i) => server.report({ gcode_state: 'RUNNING', subtask_id: `job-${i}`,
    subtask_name: 'runtime-part.3mf', mc_percent: 20 }));
  await waitSnapshot(snapshot => snapshot.events >= 11 && snapshot.runs.length === 11);
  const stateLatencyMs = performance.now() - started;
  assert.ok(stateLatencyMs < 5000, `state latency ${stateLatencyMs}`);
  assert.ok(servers.every(server => server.stats.active === 1 && server.stats.maxActive === 1));
  const command = await api('/api/three-d-printing/printers/3dprinter-huakang-a-1/commands', {
    factory_id: 'huakang-a', action: 'pause', reason: 'isolated runtime acceptance', idempotency_key: 'runtime-pause',
  });
  await waitSnapshot(snapshot => snapshot.commands.some(c => c.id === command.id && c.status === 'succeeded'));
  assert.equal(servers[0].commands.filter(c => c.command === 'pause').length, 1);
  // Read the actual authenticated HTTP SSE stream, including reconnect reset.
  const stream = await fetch(base + '/api/three-d-printing/live/events?factory_id=huakang-a', {
    headers: { Cookie: process.env.THREE_D_TEST_COOKIE, 'Last-Event-ID': 'before-outage' },
  });
  assert.equal(stream.status, 200);
  const reader = stream.body.getReader();
  const first = new TextDecoder().decode((await reader.read()).value);
  assert.ok(first.includes('event: reset') && first.includes('PAUSE'));
  assert.ok(!first.includes('credential_ref'));
  await reader.cancel();

  // Kill one owner gracefully: the other instance picks up without a second live session.
  await workers[0].stop();
  await until(() => workers[1].readyCount === 11, 10000);
  servers.forEach((server, i) => server.report({ gcode_state: 'RUNNING', subtask_id: `job-${i}` }));
  await waitSnapshot(snapshot => snapshot.printers.every(p => p.connected));

  // Logical 30-minute VPN outage; clocks advance without a 30-minute wall-time wait.
  servers.forEach(server => server.outage());
  await api('/_test/advance', { seconds: 1800, healthy: false }); await workers[1].advance();
  await waitSnapshot(snapshot => snapshot.printers.every(p => p.state === 'STALE'));
  await until(() => workers[1].readyCount === 0 && servers.every(server => server.stats.active === 0), 10000);
  let snapshot = await api('/_test/snapshot');
  assert.equal(snapshot.runs.length, 11);
  assert.ok(snapshot.runs.every(r => !r.print_end_at));
  const eventsBeforeRecovery = snapshot.events;
  await api('/_test/advance', { seconds: 0, healthy: true });
  await until(() => workers[1].readyCount === 11, 10000);
  servers.forEach((server, i) => server.report({ gcode_state: 'RUNNING', subtask_id: `job-${i}` }));
  await waitSnapshot(value => value.events >= eventsBeforeRecovery + 11 && value.printers.every(p => p.state === 'RUNNING'));
  servers.forEach((server, i) => server.report({ gcode_state: i === 10 ? 'FAILED' : 'FINISH', subtask_id: `job-${i}` }));
  snapshot = await waitSnapshot(value => value.runs.every(r => r.print_end_at));
  assert.equal(snapshot.runs.length, 11);
  assert.equal(snapshot.runs.filter(r => r.run_status === 'failed').length, 1);
  assert.equal(servers[0].commands.length, 1);
  process.stdout.write(JSON.stringify({ printers: 11, replicas: 2, commands: 1, runs: 11,
    logicalOutageMinutes: 30, stateLatencyMs: Math.round(stateLatencyMs), sse: 'passed' }) + '\n');
} finally {
  await Promise.allSettled(workers.map(worker => worker.stop()));
  await Promise.allSettled(servers.map(server => server.close()));
}
