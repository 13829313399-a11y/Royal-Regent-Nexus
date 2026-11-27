'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');
const {JSDOM} = require('jsdom');

function withFakeTimers(html) {
  const dom = new JSDOM(html, {runScripts: 'outside-only', url: 'https://qc.example.test'});
  const w = dom.window;
  let now = 1, counter = 0;
  const timers = new Map();
  w.setTimeout = (fn, delay) => { timers.set(++counter, {fn, due: now + delay}); return counter; };
  w.clearTimeout = id => timers.delete(id);
  function advance(ms) {
    const end = now + ms;
    for (;;) {
      const next = [...timers].sort((a, b) => a[1].due - b[1].due)[0];
      if (!next || next[1].due > end) break;
      const [id, {fn, due}] = next;
      timers.delete(id);
      now = due;
      fn();
    }
    now = end;
  }
  w.eval(readFileSync(join(__dirname, 'qc-glass-guide.js'), 'utf8'));
  return {dom, w, q: s => w.document.querySelector(s), advance};
}

test('photo balloon inflates seamlessly from toolbar, pulses arrow/circle, fades after 3s, and caps at 2 views', () => {
  const {dom, w, q, advance} = withFakeTimers(
    '<section><div id="tools"><button data-mark-tool="arrow"></button><button data-mark-tool="circle"></button></div><div id="photo"></div></section>'
  );
  try {
    const toolbar = q('#tools'), photo = q('#photo');
    const show = () => w.QcGlassGuide.photo(toolbar, {actor: 'tester'});
    const first = show();
    const bar = q('.qc-glass-guide');
    assert.ok(bar);
    assert.equal(toolbar.nextElementSibling, photo);
    assert.equal(q('.qc-guide-slot'), null);
    assert.equal(bar.querySelector('button'), null);
    assert.equal(bar.querySelector('.qc-guide-bead'), null);
    assert.ok(bar.querySelector('.qc-guide-balloon'));
    assert.ok(bar.querySelector('.qc-balloon-glass'));
    assert.equal(q('[data-mark-tool="arrow"]').classList.contains('qc-guide-origin-pulse'), true);
    assert.equal(q('[data-mark-tool="circle"]').classList.contains('qc-guide-origin-pulse'), true);
    assert.match(bar.textContent, /点上方「箭头 \/ 圆圈」可标注照片/);
    assert.equal(bar.classList.contains('qc-guide-enter'), true);
    advance(460);
    assert.equal(bar.classList.contains('qc-guide-enter'), false);
    advance(2999);
    assert.equal(bar.classList.contains('qc-guide-out'), false);
    advance(1);
    assert.equal(bar.classList.contains('qc-guide-out'), true);
    advance(949);
    assert.equal(bar.isConnected, true);
    advance(1);
    assert.equal(bar.isConnected, false);
    assert.equal(q('.qc-glass-guide'), null);

    const second = show();
    assert.ok(second);
    second.fade();
    assert.equal(q('.qc-glass-guide').classList.contains('qc-guide-out'), true);
    advance(950);
    assert.equal(q('.qc-glass-guide'), null);
    assert.equal(show(), null);
    assert.ok(first);
  } finally { dom.window.close(); }
});

test('reopening a portrait photo shows the mobile hint even after marking a photo', () => {
  const {dom,w,q} = withFakeTimers('<section><div id="tools"></div><img></section>');
  try {
    Object.defineProperty(w.document, 'visibilityState', {value:'visible'});
    Object.defineProperty(q('img'), 'naturalWidth', {value:600});
    const rect = (top, width, height) => ({top, left:0, right:width, bottom:top+height, width, height});
    q('section').getBoundingClientRect = () => rect(0,390,844);
    q('#tools').getBoundingClientRect = () => rect(10,330,52);
    q('img').getBoundingClientRect = () => rect(78,330,742);
    w.QcGlassGuide.completePhoto('phone-user');
    const guide = w.QcGlassGuide.photo(q('#tools'), {actor:'phone-user', mobile:true});
    assert.ok(guide);
    assert.equal(q('.qc-guide-photo').classList.contains('qc-guide-no-room'), false);
    assert.ok(q('.qc-guide-balloon').style.top);
    guide.destroy();
  } finally { dom.window.close(); }
});

test('review guide uses an existing toolbar gap when it would cover the table', () => {
  const {dom, w, q, advance} = withFakeTimers(
    '<div class="qis-review-surface"><div id="qis-review-controls"><div class="qis-review-tabs"></div><div class="qis-review-batch-actions"><button class="wb-open"></button></div></div><div id="reviewTableWrap"></div></div>'
  );
  try {
    const surface = q('.qis-review-surface'), controls = q('#qis-review-controls'), opener = q('.wb-open');
    surface.getBoundingClientRect = () => ({left: 0, top: 0, right: 1000, bottom: 600, width: 1000, height: 600});
    controls.getBoundingClientRect = () => ({left: 0, top: 0, right: 1000, bottom: 54, width: 1000, height: 54});
    opener.getBoundingClientRect = () => ({left: 952, top: 9, right: 988, bottom: 45, width: 36, height: 36});
    const tabs = {left: 12, top: 9, right: 210, bottom: 45, width: 198, height: 36};
    const actions = {left: 870, top: 9, right: 988, bottom: 45, width: 118, height: 36};
    const table = {left: 0, top: 54, right: 1000, bottom: 600, width: 1000, height: 546};
    q('.qis-review-tabs').getBoundingClientRect = () => tabs;
    q('.qis-review-batch-actions').getBoundingClientRect = () => actions;
    q('#reviewTableWrap').getBoundingClientRect = () => table;
    w.QcGlassGuide.review(controls, {anchor: opener, unread: 3, read: 2, selected: 0});
    const bar = q('.qc-glass-guide');
    const balloon = bar.querySelector('.qc-guide-balloon');
    assert.ok(bar);
    assert.equal(controls.nextElementSibling, q('#reviewTableWrap'));
    assert.equal(bar.parentElement, surface);
    assert.equal(opener.classList.contains('qc-guide-origin-pulse'), true);
    const left = parseInt(balloon.style.left), top = parseInt(balloon.style.top);
    assert.ok(left > tabs.right && left + parseInt(balloon.style.width) < actions.left);
    assert.ok(top + parseInt(balloon.style.height) < table.top);
    assert.equal(bar.querySelector('button'), null);
    assert.match(bar.textContent, /新上传 3 条/);
    assert.match(bar.textContent, /已读 2 条/);
    advance(460 + 3000);
    assert.equal(bar.classList.contains('qc-guide-out'), true);
    advance(950);
    assert.equal(bar.isConnected, false);
  } finally { dom.window.close(); }
});

test('mobile keeps a batch in the list and previews only one accepted local photo', async () => {
  const source = readFileSync(join(__dirname, 'mobile-inspection/app.js'), 'utf8');
  const row = {photos: []}, opened = [];
  let saveOk = true, saved = 0;
  const context = {
    current: row, busy: false, maxPhotoBytes: 1024, sheet: {open: false}, state: () => ({}),
    newPhotoId: () => String(row.photos.length + opened.length), refreshEntryStatus() {}, renderPhotos() {},
    change: async () => { saved++; return saveOk; }, showPhoto: p => opened.push(p.name),
    remote: {findPhoto: (r, id) => r.photos.find(p => p.id === id)}
  };
  const add = runInNewContext(
    source.slice(source.indexOf('async function addPhotos'), source.indexOf("$('camera').onchange")) + '\naddPhotos',
    context
  );
  const files = (...names) => add({currentTarget: {files: names.map(name => ({name, size: 24, type: 'image/png'})), value: 'sample'}});
  await files('one.png');
  await files('two.png', 'three.png');
  saveOk = false;
  await files('unsaved.png');
  row.submittedAt = 'submitted';
  await files('read-only.png');
  assert.deepEqual(opened, ['one.png']);
  assert.deepEqual(row.photos.map(p => p.name), ['one.png', 'two.png', 'three.png', 'unsaved.png']);
  assert.equal(saved, 3);
});
