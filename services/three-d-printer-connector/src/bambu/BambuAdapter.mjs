import { EventEmitter } from 'node:events';
import { createHash, randomUUID } from 'node:crypto';
import { isIPv4 } from 'node:net';
import tls from 'node:tls';
import { Decoder, connectPacket, packet, publishBody, publishPacket, subscribePacket } from './mqtt.mjs';
import { initialStatus, mergeReport } from './status.mjs';

function privateAddress(value) {
  if (!isIPv4(value)) return false;
  const [a, b] = value.split('.').map(Number);
  return a === 10 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168);
}

/** Lease-aware protocol layer; the durable worker supplies current ownership. */
export class BambuAdapter extends EventEmitter {
  /**
   * @param {{factoryId: string, machineNo: number, host: string, printerId: string,
   * credentialRef: string, certificateFingerprint: string, controlVerified?: boolean}} config
   * @param {{secretStore?: {get: (ref: string) => {serial: string, access_code: string}},
   * leaseValid?: () => boolean, transport?: (options: import('node:tls').ConnectionOptions) => import('node:tls').TLSSocket,
   * clock?: () => number, random?: () => number, connectTimeoutMs?: number,
   * reconnectBaseMs?: number, reconnectMaxMs?: number, heartbeatMs?: number,
   * freshMs?: number, leaseCheckMs?: number}} options
   */
  constructor(config, { secretStore, leaseValid = () => false, transport = tls.connect,
    clock = () => Date.now(), random = Math.random, connectTimeoutMs = 10000,
    reconnectBaseMs = 1000, reconnectMaxMs = 30000, heartbeatMs = 10000, freshMs = 30000,
    leaseCheckMs = 250 } = {}) {
    super();
    if (config.factoryId !== 'huakang-a' || !Number.isInteger(config.machineNo) || config.machineNo < 1 || config.machineNo > 11 ||
        !privateAddress(config.host) || !/^[a-fA-F0-9]{64}$/.test(config.certificateFingerprint) ||
        !/^printer-\d{2}$/.test(config.credentialRef) || !/^[a-zA-Z0-9_-]{1,96}$/.test(config.printerId) ||
        Object.keys(config).some(key => !['factoryId', 'machineNo', 'host', 'printerId', 'credentialRef', 'certificateFingerprint', 'controlVerified'].includes(key)) ||
        (config.controlVerified !== undefined && typeof config.controlVerified !== 'boolean')) throw new Error('invalid_printer_config');
    this.config = Object.freeze({ ...config });
    this.secretStore = secretStore;
    this.leaseValid = leaseValid;
    this.transport = transport;
    this.clock = clock;
    this.random = random;
    this.connectTimeoutMs = connectTimeoutMs;
    this.reconnectBaseMs = reconnectBaseMs;
    this.reconnectMaxMs = reconnectMaxMs;
    this.heartbeatMs = heartbeatMs;
    this.freshMs = freshMs;
    this.leaseCheckMs = leaseCheckMs;
    this.stopped = true;
    this.ready = false;
    this.state = initialStatus();
    this.commands = new Map();
    this.sequence = 0;
    this.attempt = 0;
    this.wireSequence = 0;
    this.pending = null;
    this.protocolSafe = true;
  }

  ownsLease() { try { return this.leaseValid() === true; } catch { return false; } }
  start() {
    if (!this.stopped) return;
    if (!this.ownsLease()) throw new Error('leader_lease_required');
    this.stopped = false;
    this.leaseTimer = setInterval(() => { if (!this.ownsLease()) this.stop('lease_lost'); }, this.leaseCheckMs);
    this.connect();
  }

  stop(reason = 'stopped') {
    this.stopped = true;
    clearInterval(this.leaseTimer);
    clearTimeout(this.reconnectTimer);
    this.disconnect(reason);
  }

  connect() {
    if (this.stopped || !this.ownsLease()) return this.stop('lease_lost');
    this.session = randomUUID();
    this.sequence = 0;
    this.state = initialStatus();
    this.ready = false;
    this.phase = 'tls';
    this.pingOutstanding = false;
    this.protocolSafe = true;
    this.decoder = new Decoder();
    this.serial = null;
    const socket = this.transport({ host: this.config.host, port: 8883, minVersion: 'TLSv1.2', rejectUnauthorized: false });
    this.socket = socket;
    const current = () => this.socket === socket && !this.stopped;
    this.connectTimer = setTimeout(() => { if (current()) this.disconnect('handshake_timeout'); }, this.connectTimeoutMs);
    socket.on('secureConnect', () => {
      if (!current()) return;
      try {
        if (!this.ownsLease()) return this.stop('lease_lost');
        const certificate = socket.getPeerCertificate().raw;
        if (!certificate || createHash('sha256').update(certificate).digest('hex') !== this.config.certificateFingerprint.toLowerCase()) {
          return this.disconnect('certificate_mismatch');
        }
        // Credentials are neither read nor transmitted before pinned identity succeeds.
        const secret = this.secretStore.get(this.config.credentialRef);
        this.serial = secret.serial;
        this.phase = 'connack';
        socket.write(connectPacket(`rr3d_${this.session}`, secret.access_code));
      } catch { this.disconnect('authentication_setup_failed'); }
    });
    socket.on('data', chunk => {
      if (!current()) return;
      if (!this.ownsLease()) return this.stop('lease_lost');
      try { for (const frame of this.decoder.push(chunk)) { if (current()) this.onPacket(frame); } }
      catch { this.protocolSafe = false; this.disconnect('protocol_error'); }
    });
    socket.on('error', () => { if (current()) this.disconnect('transport_error'); });
    socket.on('close', () => { if (current()) this.disconnect('transport_closed'); });
  }

  disconnect(reason) {
    clearTimeout(this.connectTimer);
    clearInterval(this.pingTimer);
    const socket = this.socket;
    this.socket = null;
    this.ready = false;
    if (this.session) {
      this.state = { ...this.state, connected: false, state: 'STALE' };
      this.emitState(reason);
    }
    this.finishCommand('unknown', reason);
    socket?.destroy();
    if (!this.stopped && this.ownsLease()) {
      const base = Math.min(this.reconnectMaxMs, this.reconnectBaseMs * 2 ** Math.min(this.attempt++, 10));
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = setTimeout(() => this.connect(), base * (0.5 + this.random() * 0.5));
    }
  }

  onPacket(frame) {
    if (this.phase === 'connack') {
      if (frame.header !== 0x20 || !frame.body.equals(Buffer.from([0, 0]))) return this.disconnect('mqtt_auth_rejected');
      this.phase = 'suback';
      this.socket.write(subscribePacket(`device/${this.serial}/report`));
      return;
    }
    if (this.phase === 'suback') {
      // Brokers may send retained publishes before SUBACK; they are not live evidence.
      if ((frame.header & 0xf0) === 0x30) return;
      if (frame.header !== 0x90 || !frame.body.equals(Buffer.from([0, 1, 0]))) return this.disconnect('mqtt_subscription_rejected');
      this.phase = 'ready';
      this.ready = true;
      clearTimeout(this.connectTimer);
      this.requestFullStatus();
      this.pingTimer = setInterval(() => {
        if (!this.ownsLease()) return this.stop('lease_lost');
        if (this.pingOutstanding) return this.disconnect('mqtt_ping_timeout');
        this.pingOutstanding = true;
        this.socket?.write(packet(0xc0));
        this.requestFullStatus();
        if (this.snapshot().state === 'STALE' && this.state.state !== 'STALE') {
          this.state = { ...this.state, state: 'STALE', connected: false };
          this.emitState('status_timeout');
          this.finishCommand('unknown', 'status_timeout');
        }
      }, this.heartbeatMs);
      this.emit('ready', { printer_id: this.config.printerId, connection_session_id: this.session });
      return;
    }
    if (!this.ready) throw new Error('mqtt_unexpected_packet');
    if (frame.header === 0xd0 && frame.body.length === 0) { this.pingOutstanding = false; return; }
    if ((frame.header & 0xf0) !== 0x30) throw new Error('mqtt_unexpected_packet');
    const publication = publishBody(frame);
    if (publication.topic !== `device/${this.serial}/report`) throw new Error('mqtt_wrong_topic');
    if (publication.packetId) {
      const ack = Buffer.alloc(2); ack.writeUInt16BE(publication.packetId);
      this.socket.write(packet(0x40, ack));
    }
    if (publication.retained) return;
    let report;
    try {
      report = JSON.parse(publication.payload.toString('utf8')).print;
      if (!report) return; // Other device information is not a live print-state update.
      this.state = mergeReport(this.state, report, new Date(this.clock()).toISOString());
    } catch {
      this.protocolSafe = false;
      this.finishCommand('unknown', 'invalid_report');
      this.emit('diagnostic', { code: 'invalid_report', printer_id: this.config.printerId });
      return;
    }
    this.attempt = 0;
    if (this.state.state === 'UNKNOWN') this.protocolSafe = false;
    const event = this.emitState('device_report');
    if (this.pending && this.sequence > this.pending.sequence &&
        report.gcode_state !== undefined && this.state.state === this.pending.expected &&
        this.state.device_job_key === this.pending.jobKey) this.finishCommand('succeeded', 'state_evidence', event);
  }

  snapshot() {
    const age = this.state.observed_at ? this.clock() - Date.parse(this.state.observed_at) : Infinity;
    const stale = !this.ready || age > this.freshMs || age < 0;
    return { ...this.state, connected: !stale && this.state.connected,
      state: stale ? 'STALE' : this.state.state, status_stale: stale };
  }

  emitState(reason) {
    const event = Object.freeze({ payload_version: 1, event_id: randomUUID(), factory_id: 'huakang-a',
      printer_id: this.config.printerId, machine_no: this.config.machineNo,
      connection_session_id: this.session, sequence: ++this.sequence,
      received_at: new Date(this.clock()).toISOString(), reason, ...this.snapshot() });
    this.emit('state', event);
    return event;
  }

  requestFullStatus() {
    if (!this.ready || !this.ownsLease()) return;
    this.socket.write(publishPacket(`device/${this.serial}/request`, {
      pushing: { sequence_id: this.nextRequestSequence(), command: 'pushall' },
    }));
  }

  nextRequestSequence() {
    // Preserve the legacy firmware's decimal sequence_id wire format.
    this.wireSequence = Math.max(this.wireSequence + 1, Math.floor(this.clock()));
    return String(this.wireSequence);
  }

  execute({ commandId, leaseId, action, valid = () => false, timeoutMs = 3000 }) {
    if (!/^[a-zA-Z0-9_-]{1,96}$/.test(commandId) || !/^[a-zA-Z0-9_-]{1,96}$/.test(leaseId) ||
        !['pause', 'resume'].includes(action) || !Number.isFinite(timeoutMs) || timeoutMs < 10 || timeoutMs > 10000)
      throw new Error('invalid_command');
    const previous = this.commands.get(commandId);
    if (previous) {
      if (previous.action !== action || previous.leaseId !== leaseId) throw new Error('command_identity_conflict');
      return previous.promise;
    }
    const state = this.snapshot();
    if (this.commands.size >= 1024) throw new Error('command_history_limit');
    if (this.pending || !this.ownsLease() || valid() !== true || !this.config.controlVerified || !this.protocolSafe ||
        !state.connected || state.state !== (action === 'pause' ? 'RUNNING' : 'PAUSE')) throw new Error('command_not_permitted');
    /** @type {(result: object) => void} */
    let resolve;
    const promise = new Promise(done => { resolve = done; });
    this.pending = { commandId, leaseId, action, resolve, sequence: this.sequence, valid,
      jobKey: state.device_job_key, expected: action === 'pause' ? 'PAUSE' : 'RUNNING' };
    this.commands.set(commandId, { action, leaseId, promise });
    this.commandTimer = setTimeout(() => this.finishCommand('unknown', 'evidence_timeout'), timeoutMs);
    try {
      this.socket.write(publishPacket(`device/${this.serial}/request`, { print: {
        sequence_id: this.nextRequestSequence(), command: action,
      } }));
    } catch { this.finishCommand('unknown', 'send_uncertain'); }
    return promise;
  }

  finishCommand(status, reason, evidence = null) {
    if (!this.pending) return;
    clearTimeout(this.commandTimer);
    const pending = this.pending;
    this.pending = null;
    let valid = false;
    try { valid = this.ownsLease() && pending.valid() === true; } catch { /* fail closed */ }
    if (!valid) { status = 'unknown'; reason = 'lease_lost'; evidence = null; }
    pending.resolve({ command_id: pending.commandId, lease_id: pending.leaseId, status, reason,
      evidence: evidence ? { event_id: evidence.event_id, connection_session_id: evidence.connection_session_id,
        sequence: evidence.sequence, state: evidence.state, observed_at: evidence.observed_at } : null });
  }
}
