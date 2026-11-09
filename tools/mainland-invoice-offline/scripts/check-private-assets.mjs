import { existsSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
export function requirePrivateAssets() {
  const { required } = JSON.parse(readFileSync(join(root, 'private-assets.json'), 'utf8'));
  const missing = required.filter((asset) => {
    const path = join(root, 'public', asset.replace(/^\//, ''));
    return !existsSync(path) || !statSync(path).isFile();
  });
  if (missing.length) throw new Error(`缺少本机私有模板（${missing.length} 项）。请按 README 将获授权模板安装到 public/；仓库不提供模板、原票或演示数据。\n${missing.join('\n')}`);
  return required.length;
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  console.log(`本机私有模板检查通过：${requirePrivateAssets()} 项。生成文件含私有资产，不得作为源码提交。`);
}
