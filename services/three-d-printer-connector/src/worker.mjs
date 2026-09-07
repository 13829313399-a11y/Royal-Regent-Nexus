import { performance } from 'node:perf_hooks';
import { BambuAdapter } from './bambu/BambuAdapter.mjs';

const stateFields = ['event_id', 'sequence', 'observed_at', 'connected', 'state', 'current_file',
  'device_job_key', 'progress_percent', 'remaining_minutes', 'live_material', 'nozzle_temperature',
  'bed_temperature', 'error_code'];

/** One boot ID per process, bounded per-printer queues, no disk command replay. */
export class ConnectorWorker {
  constructor({ client, secretStore, adapterFactory = (config, options) => new BambuAdapter(config, options),
    clock = () => performance.now(), safetyMs = 3000, pollMs = 1000, log = (_entry) => {} }) {
    this.client = client; this.secretStore = secretStore; this.adapterFactory = adapterFactory;
    this.clock = clock; this.safetyMs = safetyMs; this.pollMs = pollMs; this.log = log;
    this.slots = new Map(); this.stopped = true; this.busy = false; this.heartbeatAt = -Infinity;
  }

  deadline(grant, started) {
    const duration = Date.parse(grant.leased_until) - Date.parse(grant.server_time);
    if (!Number.isFinite(duration) || duration <= this.safetyMs || duration > 30000) return 0;
    return started + duration - this.safetyMs;
  }

  valid(slot) { return !this.stopped && !slot.closed && this.clock() < slot.deadline; }
  ref(slot) { return { printer_id: slot.id, leader_lease_id: slot.lease,
    connection_session_id: slot.session }; }

  async start() {
    if (!this.stopped) return;
    this.stopped = false;
    await this.tick();
    if (!this.stopped) this.timer = setInterval(() => void this.tick(), this.pollMs);
  }

  close(slot) {
    if (slot.closed) return;
    slot.closed = true; slot.deadline = 0;
    slot.adapter?.stop('lease_lost');
    this.log({ code: 'printer_session_closed', printer_id: slot.id });
  }

  async stop() {
    this.stopped = true; clearInterval(this.timer);
    const slots = [...this.slots.values()];
    for (const slot of slots) this.close(slot);
    await Promise.allSettled(slots.map(async slot => {
      await slot.queue;
      await this.client.post('/leases/release', { printer_id: slot.id, leader_lease_id: slot.lease });
    }));
    this.slots.clear();
  }

  async tick() {
    if (this.busy || this.stopped) return;
    this.busy = true;
    try {
      if (this.clock() - this.heartbeatAt >= 10000) {
        await this.client.post('/heartbeat', { version: 'pr06-v1' });
        const { printers } = await this.client.post('/printers');
        const ids = new Set(printers.map(printer => printer.printer_id));
        for (const slot of this.slots.values()) if (!ids.has(slot.id)) this.close(slot);
        this.ids = [...ids].slice(0, 11); this.heartbeatAt = this.clock();
      }
      await Promise.allSettled((this.ids || []).map(id => this.tickPrinter(id)));
    } catch {
      // Failure of the shared API closes all sessions immediately, before server expiry.
      for (const slot of this.slots.values()) this.close(slot);
      this.log({ code: 'connector_api_unavailable' });
    } finally { this.busy = false; }
  }

  async tickPrinter(id) {
    let slot = this.slots.get(id);
    try {
      if (slot && !this.valid(slot)) {
        this.close(slot);
        // Do not reuse a still-live grant with unknown prior session generation.
        await this.client.post('/leases/release', { printer_id: id, leader_lease_id: slot.lease }).catch(() => {});
        this.slots.delete(id); slot = null;
      }
      if (!slot) {
        const started = this.clock();
        const grant = await this.client.post('/leases/acquire', { printer_id: id });
        if (!grant.acquired || this.stopped) return;
        const deadline = this.deadline(grant, started);
        if (this.clock() >= deadline || grant.port !== 8883) return;
        slot = { id, lease: grant.leader_lease_id, deadline, generation: grant.generation || 0,
          session: '', closed: false, queue: Promise.resolve(), queued: 0, commanding: false,
          adapter: null, revision: grant.connection_revision };
        this.slots.set(id, slot);
        const current = slot;
        slot.adapter = this.adapterFactory({ factoryId: 'huakang-a', printerId: id, machineNo: grant.machine_no,
          host: grant.host, credentialRef: grant.credential_ref, certificateFingerprint: grant.certificate_fingerprint,
          controlVerified: grant.control_verified === true },
        { secretStore: this.secretStore, leaseValid: () => this.valid(current) });
        slot.adapter.on('state', event => this.enqueue(current, event));
        slot.adapter.start();
        return;
      }
      if (slot.deadline - this.clock() < 20000) {
        const started = this.clock();
        const grant = await this.client.post('/leases/renew', { printer_id: id, leader_lease_id: slot.lease });
        if (!this.valid(slot) || grant.connection_revision !== slot.revision) return this.close(slot);
        slot.deadline = this.deadline(grant, started);
      }
      if (this.valid(slot) && slot.adapter.ready && slot.session && !slot.queued && !slot.commanding) {
        slot.commanding = true;
        // Commands never block leader renewal or the other ten printers.
        void this.command(slot).catch(() => this.close(slot)).finally(() => { slot.commanding = false; });
      }
    } catch { if (slot) this.close(slot); }
  }

  enqueue(slot, event) {
    if (!this.valid(slot)) return;
    if (++slot.queued > 256) return this.close(slot);
    slot.queue = slot.queue.then(async () => {
      if (!this.valid(slot)) return;
      if (slot.session !== event.connection_session_id) {
        slot.session = event.connection_session_id;
        await this.client.post('/sessions/start', { ...this.ref(slot), generation: ++slot.generation });
      }
      /** @type {Record<string, any>} */
      const payload = { ...this.ref(slot) };
      for (const key of stateFields) payload[key] = event[key];
      payload.observed_at ||= null;
      payload.progress_percent = Math.floor(payload.progress_percent);
      payload.remaining_minutes = Math.floor(payload.remaining_minutes);
      // State evidence is durable before any result ACK. Lost responses are retried identically.
      try { await this.client.post('/events', payload); }
      catch { if (!this.valid(slot)) return; await this.client.post('/events', payload); }
    }).catch(() => this.close(slot)).finally(() => { slot.queued--; });
  }

  async command(slot) {
    const ref = this.ref(slot), started = this.clock();
    const { commands, server_time } = await this.client.post('/commands/claim', ref);
    const command = commands[0];
    if (!command || !this.valid(slot) || slot.session !== ref.connection_session_id) return;
    const deadline = this.deadline({ leased_until: command.leased_until, server_time }, started);
    const valid = () => this.valid(slot) && this.clock() < deadline && slot.session === ref.connection_session_id &&
      slot.adapter.session === ref.connection_session_id;
    if (!valid()) return;
    await slot.queue;
    const commandRef = { ...ref, command_id: command.command_id, command_lease_id: command.command_lease_id };
    const dispatch = await this.client.post('/commands/dispatch', commandRef);
    if (!dispatch.send_permitted || !valid()) return;
    let result;
    try {
      result = await slot.adapter.execute({ commandId: command.command_id, leaseId: command.command_lease_id,
        action: command.action, valid, timeoutMs: Math.max(10, Math.min(3000, deadline - this.clock() - 500)) });
    } catch { result = { status: 'unknown', reason: 'send_uncertain' }; }
    await slot.queue;
    if (!valid()) return;
    const success = result.status === 'succeeded';
    const ack = { ...commandRef, status: success ? 'succeeded' : 'unknown',
      reason: success ? 'state_evidence' : ['evidence_timeout', 'lease_lost', 'send_uncertain'].includes(result.reason)
        ? result.reason : 'disconnected', evidence_event_id: success ? result.evidence.event_id : null };
    try { await this.client.post('/commands/ack', ack); }
    catch { if (valid()) await this.client.post('/commands/ack', ack); }
  }
}
