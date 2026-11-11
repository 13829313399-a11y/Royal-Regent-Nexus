'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const source = name => fs.readFileSync(path.join(__dirname, name), 'utf8');
const excel = 'vendor/xlsx-js-style.min.js';
const jspdf = 'vendor/jspdf.umd.min.js';
const canvas = 'vendor/html2canvas.min.js';
const ocr = 'vendor/tesseract/tesseract.min.js';

function fixture(t) {
  const dom = new JSDOM(source('index.html'), {
    runScripts: 'outside-only',
    url: 'http://localhost/api/qc-department/huaxing/u-test/',
  });
  t.after(() => dom.window.close());
  const w = dom.window;
  const asset = filename => w.document.querySelector('script[src="' + filename + '"]');
  const fire = (script, type) => script.dispatchEvent(new w.Event(type));
  w.eval(source('nexus-integration.js'));
  return { w, asset, fire };
}

test('Excel, PDF and OCR stay off the workbench startup path', t => {
  const { asset } = fixture(t);
  for (const filename of [excel, jspdf, canvas, ocr]) assert.equal(asset(filename), null);
});

test('concurrent Excel actions share one download and later actions reuse the library', async t => {
  const { w, asset, fire } = fixture(t);
  const first = w.QcAssets.load('excel');
  const second = w.QcAssets.load('excel');
  const script = asset(excel);
  assert.ok(script);
  assert.equal(new URL(script.src).pathname, '/api/qc-department/huaxing/u-test/' + excel);
  assert.equal(w.document.querySelectorAll('script[src="' + excel + '"]').length, 1);
  assert.equal(asset(jspdf), null);
  assert.equal(asset(canvas), null);
  assert.equal(asset(ocr), null);
  w.XLSX = {};
  fire(script, 'load');
  await Promise.all([first, second]);
  await w.QcAssets.load('excel');
  assert.equal(w.document.querySelectorAll('script[src="' + excel + '"]').length, 1);
});

test('PDF retries a failed dependency and does not download the working dependency again', async t => {
  const { w, asset, fire } = fixture(t);
  const checkDependencies = w.eval(source('report_export.js') + '\n_rptCheckDeps;');
  const toasts = [];
  w.showToast = (...args) => toasts.push(args);
  const first = checkDependencies();
  const workingScript = asset(jspdf);
  w.jspdf = { jsPDF: function () {} };
  fire(workingScript, 'load');
  const failedScript = asset(canvas);
  fire(failedScript, 'error');
  assert.equal(await first, false);
  assert.equal(asset(canvas), null);
  assert.match(toasts[0][0], /PDF.*重试|PDF.*重新尝试/);
  assert.equal(toasts[0][1], 'error');
  const second = checkDependencies();
  assert.equal(asset(jspdf), workingScript);
  const retriedScript = asset(canvas);
  assert.notEqual(retriedScript, failedScript);
  w.html2canvas = function () {};
  fire(retriedScript, 'load');
  assert.equal(await second, true);
  assert.equal(toasts.length, 1);
});

test('OCR detects a script that downloaded without exposing the required library', async t => {
  const { w, asset, fire } = fixture(t);
  const first = w.QcAssets.load('ocr');
  fire(asset(ocr), 'load');
  await assert.rejects(first, /加载失败/);
  assert.equal(asset(ocr), null);
  const retried = w.QcAssets.load('ocr');
  w.Tesseract = {};
  fire(asset(ocr), 'load');
  await retried;
});
