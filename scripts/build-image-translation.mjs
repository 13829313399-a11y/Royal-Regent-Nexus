import { cpSync, existsSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const project = resolve(root, 'shinobu-web');
if (!existsSync(resolve(project, 'node_modules/vite/package.json'))) {
  throw new Error('请先在 shinobu-web 子目录执行 npm ci，安装图片翻译的独立依赖。');
}
const npmCli = process.env.npm_execpath;
if (!npmCli) throw new Error('请通过 npm run build:image-translation 运行此脚本。');
for (const command of ['build:server', 'build:rr']) {
const result = spawnSync(process.execPath, [npmCli, 'run', command], {
  cwd: project,
  env: { ...process.env, VITE_RR_INTEGRATION: 'true' },
  stdio: 'inherit',
});
if (result.error) throw result.error;
if (result.status !== 0) process.exit(result.status ?? 1);
}
const destination = resolve(root, 'dist/image-translation');
mkdirSync(destination, { recursive: true });
cpSync(resolve(project, 'apps/web/dist'), destination, { recursive: true });
console.log('图片翻译已构建到 dist/image-translation；模型由管理员安装在服务器私有目录。');
