import { readFileSync, lstatSync } from 'node:fs';

export function readToken(file) {
  const stat = lstatSync(file);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size > 4096 ||
      (process.platform !== 'win32' && (stat.mode & 0o077))) throw new Error('invalid_token_file');
  const token = readFileSync(file, 'utf8').trim();
  if (!/^[\x21-\x7e]{32,512}$/.test(token)) throw new Error('invalid_service_token');
  return token;
}

export class ConnectorClient {
  constructor({ baseUrl, token, instanceId, fetchImpl = fetch, timeoutMs = 2500 }) {
    const url = new URL(baseUrl);
    if (url.username || url.password || url.search || url.hash ||
        (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['127.0.0.1', '[::1]', 'localhost'].includes(url.hostname))))
      throw new Error('connector_requires_https');
    this.url = url.href.replace(/\/$/, '') + '/api/internal/three-d-connector';
    this.token = token;
    this.instanceId = instanceId;
    this.fetchImpl = fetchImpl;
    this.timeoutMs = timeoutMs;
  }

  async post(path, payload = {}) {
    const response = await this.fetchImpl(this.url + path, {
      method: 'POST', redirect: 'error', signal: AbortSignal.timeout(this.timeoutMs),
      headers: { 'Content-Type': 'application/json', 'X-Three-D-Connector-Token': this.token },
      body: JSON.stringify({ protocol_version: 1, factory_id: 'huakang-a',
        site_id: '3dsite-huakang-a-heyuan', instance_id: this.instanceId, ...payload }),
    });
    // Never log upstream response bodies, URLs, tokens, or device configuration.
    if (!response.ok) throw new Error(`connector_api_${response.status}`);
    return response.json();
  }
}
