import tls from 'node:tls';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Decoder, packet, publishPacket } from '../src/bambu/mqtt.mjs';

const repository = fileURLToPath(new URL('../../../', import.meta.url));
const python = process.env.THREE_D_TEST_PYTHON || (process.platform === 'win32'
  ? path.join(repository, 'backend/.venv/Scripts/python.exe') : 'python3');
// Fresh test-only key stays in memory; no checked-in private certificate fixture.
const credentials = JSON.parse(execFileSync(python, ['-c', `
import json
from datetime import datetime, timedelta, timezone
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
n = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'isolated-test-printer')])
c = (x509.CertificateBuilder().subject_name(n).issuer_name(n).public_key(k.public_key())
 .serial_number(x509.random_serial_number()).not_valid_before(datetime.now(timezone.utc)-timedelta(minutes=1))
 .not_valid_after(datetime.now(timezone.utc)+timedelta(hours=1)).sign(k, hashes.SHA256()))
print(json.dumps({'key': k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode(), 'cert': c.public_bytes(serialization.Encoding.PEM).decode(), 'der': c.public_bytes(serialization.Encoding.DER).hex()}))
`], { encoding: 'utf8', timeout: 10000, maxBuffer: 20000 }));
export const fingerprint = createHash('sha256').update(Buffer.from(credentials.der, 'hex')).digest('hex');

export async function simulator({ acknowledge = true, connack = 0, suback = 0, fragment = false } = {}) {
  const sockets = new Set(), commands = [], requests = [];
  let connections = 0, maxActive = 0, connects = 0;
  const server = tls.createServer(credentials, socket => {
    sockets.add(socket); connections++; maxActive = Math.max(maxActive, sockets.size);
    const decoder = new Decoder();
    socket.on('error', () => {});
    socket.on('close', () => sockets.delete(socket));
    socket.on('data', data => {
      try {
        for (const frame of decoder.push(data)) {
          if (frame.header === 0x10) { connects++; socket.write(packet(0x20, Buffer.from([0, connack]))); }
          else if (frame.header === 0x82) {
            socket.write(packet(0x90, Buffer.from([0, 1, suback])));
          } else if (frame.header === 0xc0) socket.write(packet(0xd0));
          else if (frame.header === 0x30) {
            const size = frame.body.readUInt16BE();
            const topic = frame.body.subarray(2, 2 + size).toString();
            const value = JSON.parse(frame.body.subarray(2 + size).toString());
            requests.push(value);
            if (value.print) {
              commands.push(value.print);
              if (acknowledge) send(socket, { gcode_state: value.print.command === 'pause' ? 'PAUSE' : 'RUNNING' }, topic.replace('/request', '/report'));
            }
          }
        }
      } catch { socket.destroy(); }
    });
  });
  server.on('tlsClientError', () => {});
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  function send(socket, print, topic = 'device/TEST-SERIAL/report', retained = false) {
    const bytes = publishPacket(topic, { print });
    if (retained) bytes[0] |= 1;
    if (fragment) { socket.write(bytes.subarray(0, 3)); setImmediate(() => { if (!socket.destroyed) socket.write(bytes.subarray(3)); }); }
    else socket.write(bytes);
  }
  return {
    fingerprint, sockets, commands, requests,
    get port() { return server.address().port; },
    get stats() { return { connections, maxActive, connects, active: sockets.size }; },
    transport(options) { return tls.connect({ ...options, host: '127.0.0.1', port: server.address().port }); },
    report(print, { retained = false, topic } = {}) { for (const socket of sockets) send(socket, print, topic, retained); },
    raw(bytes) { for (const socket of sockets) socket.write(bytes); },
    outage() { for (const socket of sockets) socket.destroy(); },
    async close() { for (const socket of sockets) socket.destroy(); await new Promise(resolve => server.close(resolve)); },
  };
}

export async function until(predicate, timeout = 2000) {
  const deadline = Date.now() + timeout;
  while (!predicate()) {
    if (Date.now() > deadline) throw new Error('test_condition_timeout');
    await new Promise(resolve => setTimeout(resolve, 5));
  }
}
