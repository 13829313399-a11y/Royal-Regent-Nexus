/**
 * 离线单文件打包：vite build（离线配置）→ 把 JS/CSS 与内置 xlsx 模板全部内联进一个 HTML。
 * 产出 dist-offline/发票系统离线版_<日期>.html，双击用浏览器打开即可用（file:// 协议，无需服务器）。
 * 运行：node scripts/build-offline.mjs
 */
import { requirePrivateAssets } from './check-private-assets.mjs';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, readdirSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = join(root, 'dist-offline');

requirePrivateAssets();

console.log('1/3 vite build（离线配置）…');
execFileSync(process.execPath, [join(root, 'node_modules/vite/bin/vite.js'), 'build', '--config', 'vite.config.offline.mjs'], { cwd: root, stdio: 'inherit' });

console.log('2/3 内联 JS/CSS + 内置模板…');
let html = readFileSync(join(OUT, 'index.html'), 'utf8');

// 内联 <script ... src="./assets/xx.js"></script>
html = html.replace(/<script([^>]*?)\ssrc="\.\/assets\/([^"]+)"([^>]*)><\/script>/g, (m, pre, file, post) => {
  const js = readFileSync(join(OUT, 'assets', file), 'utf8').replace(/<\/script/gi, '<\\/script');
  return `<script${pre}${post}>\n${js}\n</script>`;
});
// 内联 <link rel="stylesheet" href="./assets/xx.css">
html = html.replace(/<link([^>]*?)rel="stylesheet"([^>]*?)href="\.\/assets\/([^"]+)"([^>]*?)\/?>/g, (m, a, b, file, c) => {
  const css = readFileSync(join(OUT, 'assets', file), 'utf8').replace(/<\/style/gi, '<\\/style');
  return `<style>\n${css}\n</style>`;
});
// 清掉残余的 modulepreload / favicon 外链
html = html.replace(/<link[^>]*rel="modulepreload"[^>]*>/g, '');

// 内置 xlsx 模板 → base64 内嵌（键 = 运行时 fetch 路径）
const ASSET_FILES = [
  ['/base-master.xlsx', join(root, 'public/base-master.xlsx')],
  ['/miandan-tpl.xlsx', join(root, 'public/miandan-tpl.xlsx')],
  ['/hdd-ledger-tpl.xlsx', join(root, 'public/hdd-ledger-tpl.xlsx')],
  ['/zuru-tpl/兴信-zuru.xlsx', join(root, 'public/zuru-tpl/兴信-zuru.xlsx')],
  ...readdirSync(join(root, 'public/other-tpl')).map((f) => [`/other-tpl/${f}`, join(root, 'public/other-tpl', f)]),
  ...readdirSync(join(root, 'public/hkb-tpl')).map((f) => [`/hkb-tpl/${f}`, join(root, 'public/hkb-tpl', f)]),
  ...readdirSync(join(root, 'public/hka-tpl')).map((f) => [`/hka-tpl/${f}`, join(root, 'public/hka-tpl', f)]),
  ...readdirSync(join(root, 'public/hkd-tpl')).map((f) => [`/hkd-tpl/${f}`, join(root, 'public/hkd-tpl', f)]),
  ...readdirSync(join(root, 'public/hx-tpl')).map((f) => [`/hx-tpl/${f}`, join(root, 'public/hx-tpl', f)]),
  ...readdirSync(join(root, 'public/hd-tpl')).map((f) => [`/hd-tpl/${f}`, join(root, 'public/hd-tpl', f)]),
];
const assetsObj = ASSET_FILES.map(([k, p]) => `${JSON.stringify(k)}:${JSON.stringify(readFileSync(p).toString('base64'))}`).join(',');
const inject = `<script>window.__OFFLINE_ASSETS__={${assetsObj}};</script>`;
const scriptIdx = html.search(/<script/);
if (scriptIdx < 0) throw new Error('index.html 里没找到 <script>');
html = html.slice(0, scriptIdx) + inject + html.slice(scriptIdx);

// 自检：不应再有指向本地文件的 src/href
const leftovers = html.match(/(?:src|href)="\.\/assets\/[^"]+"/g);
if (leftovers) throw new Error(`还有未内联的本地资源: ${leftovers.join(', ')}`);

const now = new Date();
const stamp = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`;
const outFile = join(OUT, `发票系统离线版_${stamp}.html`);
writeFileSync(outFile, html);
const mb = (statSync(outFile).size / 1024 / 1024).toFixed(1);
console.log(`3/3 完成: ${outFile}（${mb} MB）`);
