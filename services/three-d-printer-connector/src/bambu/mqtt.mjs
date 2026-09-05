// Extracted from edge/three-d-printing-agent/agent.js; strict bounded framing.
export const MAX_PACKET_BYTES = 65536;

export function mqttString(value) {
  const bytes = Buffer.from(value, 'utf8');
  if (bytes.length > 65535) throw new Error('mqtt_string_limit');
  const size = Buffer.alloc(2);
  size.writeUInt16BE(bytes.length);
  return Buffer.concat([size, bytes]);
}

export function packet(header, body = Buffer.alloc(0)) {
  if (body.length > MAX_PACKET_BYTES) throw new Error('mqtt_packet_limit');
  const length = [];
  let size = body.length;
  do {
    const byte = size % 128;
    size = Math.floor(size / 128);
    length.push(byte | (size ? 128 : 0));
  } while (size);
  return Buffer.concat([Buffer.from([header, ...length]), body]);
}

export function connectPacket(clientId, password) {
  return packet(0x10, Buffer.concat([
    mqttString('MQTT'), Buffer.from([4, 0xc2, 0, 60]),
    mqttString(clientId), mqttString('bblp'), mqttString(password),
  ]));
}

export const subscribePacket = topic => packet(0x82,
  Buffer.concat([Buffer.from([0, 1]), mqttString(topic), Buffer.from([0])]));
export const publishPacket = (topic, body) => packet(0x30,
  Buffer.concat([mqttString(topic), Buffer.from(JSON.stringify(body))]));

export class Decoder {
  buffer = Buffer.alloc(0);
  push(chunk) {
    if (chunk.length + this.buffer.length > MAX_PACKET_BYTES * 2 + 10) throw new Error('mqtt_buffer_limit');
    this.buffer = Buffer.concat([this.buffer, chunk]);
    const frames = [];
    while (this.buffer.length >= 2) {
      let size = 0, cursor = 1, complete = false;
      for (let n = 0; n < 4; n++) {
        if (cursor >= this.buffer.length) return frames;
        const digit = this.buffer[cursor++];
        size += (digit & 127) * 128 ** n;
        if (size > MAX_PACKET_BYTES) throw new Error('mqtt_packet_limit');
        if (!(digit & 128)) { complete = true; break; }
      }
      if (!complete) throw new Error('mqtt_malformed_length');
      if (cursor + size > this.buffer.length) break;
      frames.push({ header: this.buffer[0], body: this.buffer.subarray(cursor, cursor + size) });
      this.buffer = this.buffer.subarray(cursor + size);
    }
    return frames;
  }
}

export function publishBody(frame) {
  const qos = (frame.header >> 1) & 3;
  if (qos > 1 || frame.body.length < 2) throw new Error('mqtt_unsupported_publish');
  const length = frame.body.readUInt16BE();
  const offset = 2 + length + (qos ? 2 : 0);
  if (!length || offset > frame.body.length) throw new Error('mqtt_invalid_topic');
  const packetId = qos ? frame.body.readUInt16BE(2 + length) : null;
  if (qos && !packetId) throw new Error('mqtt_invalid_packet_id');
  return { topic: frame.body.subarray(2, 2 + length).toString('utf8'),
    payload: frame.body.subarray(offset), packetId, retained: Boolean(frame.header & 1) };
}
