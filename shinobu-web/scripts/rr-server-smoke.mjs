import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const output = resolve(process.env.RR_SMOKE_OUTPUT ?? '../outputs/image-translation-qa/server-browser');
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const context = await browser.newContext({ viewport: { width: 1380, height: 900 }, acceptDownloads: true });
let account = 'qa-alice';
const errors = [], requests = [];
await context.route('**/api/**', async route => {
  const original = route.request();
  await route.continue({ headers: { ...original.headers(), 'x-qa-account': account } });
});
// Deliberately emulate ordinary HTTP: no OPFS or browser inference may be required.
await context.addInitScript(() => {
  Object.defineProperty(globalThis, 'isSecureContext', { value: false, configurable: true });
  if (navigator.storage) Object.defineProperty(navigator.storage, 'getDirectory', { value: () => { throw new Error('OPFS forbidden in server UI'); } });
});
const page = await context.newPage();
page.on('pageerror', error => errors.push(error.message));
page.on('request', req => requests.push(new URL(req.url()).pathname));
try {
  await page.goto('http://127.0.0.1:8001/image-translation/?factory=group');
  await page.getByText('无需安装，上传即可处理').waitFor();
  if (await page.getByText('API Key', { exact: true }).count()) throw new Error('API key control remained');
  await page.locator('input[type=file]').setInputFiles(resolve('../outputs/image-translation-qa/server/source.png'));
  await page.getByRole('button', { name: '开始翻译（1 个文件）', exact: true }).waitFor();
  await page.getByRole('button', { name: '开始翻译（1 个文件）', exact: true }).click();
  await page.locator('.rs-download').first().waitFor({ timeout: 240000 });
  await page.locator('.rs-image-wrap img').waitFor();
  await page.locator('.rs-review summary').waitFor();
  await page.locator('.rs-review summary').click();
  await page.locator('.rs-review-list button').first().click();
  await page.locator('.rs-selection').waitFor();
  await page.getByLabel('预览缩放').selectOption('2');
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error('Zoom overflowed the page');
  await page.getByLabel('预览缩放').selectOption('1');
  await page.locator('.rs-review summary').click();
  const pdfEvent = page.waitForEvent('download');
  await page.locator('.rs-download').first().click();
  await (await pdfEvent).saveAs(resolve(output, 'translation.pdf'));
  await page.screenshot({ path: resolve(output, 'workbench.png'), fullPage: true });
  const priorId = await page.locator('.rs-download').first().getAttribute('href');
  await page.getByRole('button', { name: '框选补翻', exact: true }).click();
  const bounds = await page.locator('.rs-image-wrap img').boundingBox();
  await page.mouse.move(bounds.x + bounds.width * .04, bounds.y + bounds.height * .18);
  await page.mouse.down();
  await page.mouse.move(bounds.x + bounds.width * .65, bounds.y + bounds.height * .4, { steps: 5 });
  await page.mouse.up();
  await page.getByRole('button', { name: '提交补翻', exact: true }).click();
  await page.locator('.rs-task').getByText('已完成 · 第 2 版', { exact: true }).waitFor({ timeout: 240000 });
  if (await page.locator('.rs-items>button').count() !== 1) throw new Error('Patch duplicated export queue');
  await page.getByRole('button', { name: '汇总导出 PDF', exact: true }).click();
  await page.getByRole('link', { name: '下载 图片翻译汇总.pdf', exact: true }).waitFor({ timeout: 30000 });
  const aggregateEvent = page.waitForEvent('download');
  await page.getByRole('link', { name: '下载 图片翻译汇总.pdf', exact: true }).click();
  await (await aggregateEvent).saveAs(resolve(output, 'combined.pdf'));
  await page.reload();
  await page.getByRole('button', { name: '我的历史', exact: true }).click();
  await page.locator('.rs-history-row').first().waitFor();
  await page.screenshot({ path: resolve(output, 'history.png'), fullPage: true });
  await page.locator('.rs-history-row').first().click();
  await page.locator('.rs-image-wrap img').waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: resolve(output, 'mobile.png'), fullPage: true });
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error('Mobile horizontal overflow');
  account = 'qa-bob';
  await page.reload();
  await page.getByRole('button', { name: '我的历史', exact: true }).click();
  await page.getByText('暂无翻译记录', { exact: true }).waitFor();
  const response = await context.request.get('http://127.0.0.1:8001' + priorId, { headers: { 'x-qa-account': account } });
  if (response.status() !== 404) throw new Error('Cross-account artifact exposure');
  if (requests.some(path => /\.wasm$|\/models\/|onnxWorker|pipeline\.worker/.test(path))) throw new Error('Client downloaded inference assets');
  if (errors.length) throw new Error(errors.join('\n'));
  await writeFile(resolve(output, 'report.json'), JSON.stringify({ realServerInference: true, patchAndSingleExport: true,
    reviewLocalization: true, zoomContained: true,
    httpWithoutOpfs: true, refreshHistory: true, crossAccountIsolation: true, noBrowserModels: true, mobileOverflow: false, errors }, null, 2));
  console.log('SERVER_BROWSER_SMOKE_PASSED');
} catch (error) {
  await page.screenshot({ path: resolve(output, 'failure.png'), fullPage: true });
  await writeFile(resolve(output, 'failure.txt'), await page.locator('body').innerText());
  throw error;
} finally { await browser.close(); }
