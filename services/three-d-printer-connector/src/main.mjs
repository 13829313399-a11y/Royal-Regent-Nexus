import { randomUUID } from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { ConnectorClient, readToken } from './client.mjs';
import { FileSecretStore } from './secrets.mjs';
import { ConnectorWorker } from './worker.mjs';

export async function main(env = process.env) {
  const worker = new ConnectorWorker({
    client: new ConnectorClient({ baseUrl: env.THREE_D_API_URL,
      token: readToken(env.THREE_D_CONNECTOR_TOKEN_FILE), instanceId: randomUUID() }),
    secretStore: new FileSecretStore(env.THREE_D_SECRET_DIR),
    log: entry => process.stdout.write(JSON.stringify(entry) + '\n'),
  });
  let closing = false;
  const shutdown = async () => {
    if (closing) return; closing = true;
    await worker.stop();
    process.off('SIGINT', shutdown); process.off('SIGTERM', shutdown);
  };
  process.on('SIGINT', shutdown); process.on('SIGTERM', shutdown);
  await worker.start();
  return worker;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(() => { process.stderr.write('connector_startup_failed\n'); process.exitCode = 1; });
}
