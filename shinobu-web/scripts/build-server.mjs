import { build } from 'esbuild';
import { mkdir, readFile, writeFile, copyFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import wawoff2 from 'wawoff2';

const root = resolve(import.meta.dirname, '..');
const out = resolve(root, 'server/dist');
await mkdir(resolve(out, 'fonts'), { recursive: true });
await build({ entryPoints: [resolve(root, 'server/runner.ts')], outfile: resolve(out, 'runner.mjs'),
  bundle: true, platform: 'node', target: 'node24', format: 'esm',
  external: ['canvas', 'onnxruntime-node'],
  banner: { js: "import { createRequire } from 'node:module'; const require = createRequire(import.meta.url);" } });
await copyFile(resolve(root, 'public/models/models.json'), resolve(out, 'models.json'));
for (const name of ['SourceHanSansCN-VF.ttf', 'SourceHanSansTW-VF.ttf']) {
  const font = await readFile(resolve(root, 'public/fonts', `${name}.woff2`));
  await writeFile(resolve(out, 'fonts', name), await wawoff2.decompress(font));
}
console.log('Server image pipeline built. Model weights remain in private server storage.');
