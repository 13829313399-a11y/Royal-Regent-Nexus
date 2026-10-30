import { performance } from 'node:perf_hooks';
import { BambuAdapter } from './bambu/BambuAdapter.mjs';

const stateFields = ['event_id', 'sequence', 'observed_at', 'connected', 'state', 'current_file',
  'device_job_key', 'progress_percent', 'remaining_minutes', 'live_material', 'nozzle_temperature',
  'bed_temperature', 'nozzle_target', 'bed_target', 'layer_num', 'total_layers', 'error_code'];

// Emit only fixed diagnostic codes, never exception bodies, URLs or credentials.
function apiFailure(error) {
  if (/^connector_api_[1-5]\d\d$/.test(error?.message)) return error.message;
  if (['TimeoutError', 'AbortError'].includes(error?.name)) return 'api_timeout';
  return 'api_request_failed';
}
const connectionReasons = new Set(['device_report', 'tcp_connect_timeout', 'tls_handshake_timeout',
  'mqtt_handshake_timeout', 'certificate_mismatch', 'authentication_setup_failed', 'transport_error',
  'transport_closed', 'protocol_error', 'mqtt_auth_rejected', 'mqtt_subscription_rejected',
  'mqtt_ping_timeout', 'status_timeout']);

/** One boot ID per process, bounded per-printer queues, no disk command replay. */
export class ConnectorWorker {
  constructor({ client, secretStore, adapterFactory = (config, options) => new BambuAdapter(config, options),
    clock = () => performance.now(), safetyMs = 3000, pollMs = 1000, log = (_entry) => {} }) {
    this.client = client; this.secretStore = secretStore; this.adapterFactory = adapterFactory;
    this.clock = clock; this.safetyMs = safetyMs; this.pollMs = pollMs; this.log = log;
    this.slots = new Map(); this.stopped = true; this.busy = false; this.heartbeatAt = -Infinity;
    this.apiRetryAt = 0; this.apiFailures = 0;
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

  close(slot, reason = 'lease_lost') {
    if (slot.closed) return;
    slot.closed = true; slot.deadline = 0;
    slot.adapter?.stop('lease_lost');
    this.log({ code: 'printer_session_closed', printer_id: slot.id, reason });
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
    if (this.busy || this.stopped || this.clock() < this.apiRetryAt) return;
    this.busy = true;
    try {
      if (this.clock() - this.heartbeatAt >= 10000) {
        await this.client.post('/heartbeat', { version: 'pr06-v1' });
        const { printers } = await this.client.post('/printers');
        const ids = new Set(printers.map(printer => printer.printer_id));
        for (const slot of this.slots.values()) if (!ids.has(slot.id)) this.close(slot);
        this.ids = [...ids].slice(0, 16); this.heartbeatAt = this.clock();
        if (this.apiFailures) this.log({ code: 'connector_api_recovered' });
        this.apiFailures = 0; this.apiRetryAt = 0;
      }
      await Promise.allSettled((this.ids || []).map(id => this.tickPrinter(id)));
    } catch (error) {
      // Failure of the shared API closes all sessions immediately, before server expiry.
      for (const slot of this.slots.values()) this.close(slot, 'shared_api_unavailable');
      const retryMs = Math.min(15000, 1000 * 2 ** Math.min(this.apiFailures++, 4));
      this.apiRetryAt = this.clock() + retryMs;
      this.log({ code: 'connector_api_unavailable', reason: apiFailure(error), retry_ms: retryMs });
    } finally { this.busy = false; }
  }

  async tickPrinter(id) {
    let slot = this.slots.get(id);
    let operation = 'acquire';
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
          adapter: null, revision: grant.connection_revision, controlVerified: grant.control_verified === true,
          diagnosticKey: '', diagnosticAt: -Infinity };
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
        operation = 'renew';
        const started = this.clock();
        const grant = await this.client.post('/leases/renew', { printer_id: id, leader_lease_id: slot.lease });
        if (!this.valid(slot) || grant.connection_revision !== slot.revision) return this.close(slot);
        slot.deadline = this.deadline(grant, started);
      }
      if (this.valid(slot) && slot.controlVerified && slot.adapter.ready && slot.session && !slot.queued && !slot.commanding) {
        slot.commanding = true;
        // Commands never block leader renewal or the other printers.
        void this.command(slot).catch(error => {
          this.log({ code: 'printer_api_failed', printer_id: id, operation: 'command', reason: apiFailure(error) });
          this.close(slot, 'command_api_failed');
        }).finally(() => { slot.commanding = false; });
      }
    } catch (error) {
      this.log({ code: 'printer_api_failed', printer_id: id, operation, reason: apiFailure(error) });
      if (slot) this.close(slot, 'printer_api_failed');
    }
  }

  enqueue(slot, event) {
    if (!this.valid(slot)) return;
    const reason = connectionReasons.has(event.reason) ? event.reason : 'device_state';
    const key = `${event.connected === true}:${reason}`;
    if (key !== slot.diagnosticKey || (event.connected !== true && this.clock() - slot.diagnosticAt >= 60000)) {
      this.log({ code: event.connected === true ? 'printer_telemetry_recovered' : 'printer_connection_failed',
        printer_id: slot.id, reason });
      slot.diagnosticKey = key; slot.diagnosticAt = this.clock();
    }
    if (++slot.queued > 256) return this.close(slot, 'event_queue_overflow');
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
    }).catch(error => {
      this.log({ code: 'printer_api_failed', printer_id: slot.id, operation: 'event', reason: apiFailure(error) });
      this.close(slot, 'event_upload_failed');
    }).finally(() => { slot.queued--; });
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
