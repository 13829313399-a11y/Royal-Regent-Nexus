import { chromium } from '@playwright/test';
import { createCanvas } from 'canvas';
import { PDFDocument } from 'pdf-lib';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';

// Use a disposable browser and a synthetic account; never reuse an employee session.
const origin = process.env.RR_SMOKE_ORIGIN ?? 'http://127.0.0.1:5173';
const output = resolve(process.env.RR_SMOKE_OUTPUT ?? '../outputs/image-translation-qa');
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 960 }, acceptDownloads: true });
let account = 'rr-smoke-a';
await context.route(`${origin}/api/auth/me`, route => route.fulfill({
  json: { id: account, force_password_change: false },
}));
const page = await context.newPage();
page.setDefaultTimeout(30_000);
const errors = [];
page.on('pageerror', error => errors.push(error.message));
page.on('console', message => { if (message.type() === 'error') console.log('browser:', message.text()); });
const report = { checks: [], errors };
try {
  await page.goto(`${origin}/image-translation/?factory=huaxing`);
  await page.getByRole('link', { name: '返回公共工具栏' }).waitFor();
  assert.equal(await page.getByRole('link', { name: '返回公共工具栏' }).getAttribute('href'), '/tools?factory=huaxing');
  assert.equal(await page.evaluate(() => crossOriginIsolated), true);
  assert.deepEqual(await page.evaluate(async () => (await navigator.serviceWorker.getRegistrations()).map(item => item.scope)), []);
  report.checks.push('subdirectory assets, isolated document, return link, no root service worker');
  await page.screenshot({ path: resolve(output, 'workbench.png'), fullPage: true });
  console.log('Opened integrated workbench.');

  if (process.env.RR_SMOKE_MODEL_DIR) {
    const manifest = JSON.parse(await readFile('packages/model-manifest/manifest.json', 'utf8'));
    await page.getByLabel('导入模型文件').setInputFiles(
      manifest.assets.map(asset => resolve(process.env.RR_SMOKE_MODEL_DIR, asset.path)),
    );
    await page.waitForFunction(async () => {
      const root = await navigator.storage.getDirectory();
      try {
        const app = await root.getDirectoryHandle('shinobu-translator');
        const models = await app.getDirectoryHandle('model-packages');
        const receipt = await models.getFileHandle('current.json');
        return (await receipt.getFile()).size > 0;
      } catch { return false; }
    }, undefined, { timeout: 180_000 });
    report.checks.push('import and SHA-256 verification of local model files');
    console.log('Models imported.');

    await page.getByRole('radio', { name: '原文', exact: true }).click();
    const canvas = createCanvas(1000, 600);
    const draw = canvas.getContext('2d');
    draw.fillStyle = '#ffffff';
    draw.fillRect(0, 0, 1000, 600);
    draw.fillStyle = '#111111';
    draw.font = '48px Arial';
    draw.fillText('QUALITY CONTROL', 120, 200);
    draw.fillText('CHECK EVERY PART', 120, 290);
    const sample = resolve(output, 'sample.png');
    await writeFile(sample, canvas.toBuffer('image/png'));
    await page.locator('#web-image-import').setInputFiles(sample);
    await page.locator('.queue-item').waitFor();
    console.log('Synthetic image queued.');
    await page.screenshot({ path: resolve(output, 'queued.png'), fullPage: true });
    const start = page.getByRole('button', { name: /开始处理|开始翻译|开始去字|开始排版/ }).first();
    await Promise.race([
      start.waitFor({ timeout: 180_000 }),
      page.getByText('生产模型能力测试失败，不能启动任务', { exact: true }).waitFor({ timeout: 180_000 })
        .then(() => { throw new Error('Production model probe failed.'); }),
    ]);
    await start.click({ timeout: 120_000 });
    const pdf = page.getByRole('button', { name: '汇总导出 PDF', exact: true });
    await pdf.waitFor();
    await page.waitForFunction(() => Array.from(document.querySelectorAll('button'))
      .some(button => button.textContent?.trim() === '汇总导出 PDF' && !button.disabled), undefined, { timeout: 240_000 });
    const downloadEvent = page.waitForEvent('download');
    await pdf.click();
    const download = await downloadEvent;
    const pdfPath = resolve(output, 'result.pdf');
    await download.saveAs(pdfPath);
    const result = await PDFDocument.load(await readFile(pdfPath));
    assert.equal(result.getPageCount(), 1);
    assert.equal(result.getPage(0).getWidth() / result.getPage(0).getHeight(), 1000 / 600);
    report.checks.push('real OCR, erase, original-text typesetting, one-page PDF with original aspect ratio');
    console.log('Real inference and PDF export passed.');
    await page.screenshot({ path: resolve(output, 'result.png'), fullPage: true });
  }
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  assert.equal(await page.evaluate(() => {
    const header = document.querySelector('.topbar').getBoundingClientRect();
    return [...document.querySelectorAll('.topbar-actions .mobile-view-trigger')].every(button => {
      const bounds = button.getBoundingClientRect();
      return bounds.top >= header.top && bounds.bottom <= header.bottom;
    });
  }), true);
  report.checks.push('mobile header fits without covering the workbench');
  await page.screenshot({ path: resolve(output, 'mobile.png'), fullPage: true });
  account = 'rr-smoke-b';
  await page.reload();
  await page.getByRole('link', { name: '返回公共工具栏' }).waitFor();
  assert.equal(await page.locator('.queue-item').count(), 0);
  report.checks.push('second account opens its own empty workspace');
  assert.deepEqual(errors, []);
} catch (error) {
  report.failure = error.stack ?? String(error);
  await page.screenshot({ path: resolve(output, 'failure.png'), fullPage: true });
  await writeFile(resolve(output, 'page.txt'), await page.locator('body').innerText());
  throw error;
} finally {
  await writeFile(resolve(output, 'report.json'), JSON.stringify(report, null, 2));
  await browser.close();
}
