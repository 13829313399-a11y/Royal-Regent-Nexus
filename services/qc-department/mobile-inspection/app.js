'use strict';

const $ = id => document.getElementById(id);
const all = selector => [...document.querySelectorAll(selector)];
const fieldLabels = { problem: '验货问题', remark: '备注' };
const fieldIds = Object.keys(fieldLabels);
const resultValues = ['PASS', 'FAIL', 'PENDING', 'LG'];
const maxPhotoBytes = 10 * 1024 * 1024;
const app = $('app');
const entryScroll = $('entry-scroll');
const taskScroll = $('task-scroll');
const sheet = $('sheet');
const editor = $('editor');
const composer = $('composer');
const wideScreen = window.matchMedia?.('(min-width: 840px) and (hover: hover) and (pointer: fine)');

const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
})[char]);
const icon = name => '<svg aria-hidden="true"><use href="#i-' + name + '"/></svg>';
const dateLabel = day => day ? Number(day.slice(5, 7)) + '月' + Number(day.slice(8)) + '日' : '未排日期';
const planDate = row => row.start && row.dateTo && row.dateTo !== row.start
  ? row.start + ' 至 ' + row.dateTo
  : row.start || row.dateTo || '';
const remote = window.QcMobileRemote;

let db;
let rows = [];
let page = 'tasks';
let current;
let entryFrom = 'tasks';
let listPosition = 0;
let progressFilter = 'all';
let desktopReceipt = '';
let seenReturned = false;
let activeField = '';
let composing = false;
let editorTrigger;
let unoccludedHeight = 0;
let viewportWidth = 0;
const editorSelections = new Map();
const composingNotes = new WeakSet();
let saving = Promise.resolve();
const queuedSnapshots = new Set();
let photoUrls = new Map();
let photoCanClose = null;
let dialogTrigger;
let busy = false;
let openingTask = false;
const writeState = new Map();

function state(row) {
  if (!writeState.has(row.id)) {
    const version = row._v || 0;
    writeState.set(row.id, { version, saved: row._pending ? version - 1 : version, localSaved: -1, requested: -1, pending: 0, error: row._syncError || '', localError: '', photoError: '', values:remote.values(row), fields:Object.fromEntries((row._pending?remote.dirtyFields(row):[]).map(k=>[k,version])) });
  }
  return writeState.get(row.id);
}

function openDatabase() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(remote.cacheKey, 1);
    req.onupgradeneeded = () => req.result.createObjectStore('tasks', { keyPath: 'id' });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
    req.onblocked = () => reject(new Error('无法打开本机存储'));
  });
}

function readRows() {
  return new Promise((resolve, reject) => {
    const request = db.transaction('tasks').objectStore('tasks').getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function localWriteRows(items) {
  if (!db) return Promise.reject(new Error('本机存储不可用'));
  return new Promise((resolve, reject) => {
    const tx = db.transaction('tasks', 'readwrite');
    const tasks = tx.objectStore('tasks');
    for (const row of items) {
      const get = tasks.get(row.id);
      get.onsuccess = () => { if (!get.result || (get.result._v || 0) <= (row._v || 0)) tasks.put(row); };
    }
    tx.oncomplete = () => resolve();
    tx.onabort = () => reject(tx.error || new Error('本机保存失败'));
    tx.onerror = () => reject(tx.error || new Error('本机保存失败'));
  });
}

function writeRows(items) { return remote.write(items, localWriteRows); }

function enqueue(items) {
  items.forEach(item=>queuedSnapshots.add(item));
  const job = saving.catch(() => {}).then(() => writeRows(items)).finally(()=>items.forEach(item=>queuedSnapshots.delete(item)));
  saving = job;
  return job;
}

function snapshot(row) {
  return { ...row, _v: state(row).version, _base:{...row._base}, _dirtyFields:Object.keys(state(row).fields), photos: row.photos.map(photo => ({ ...photo })) };
}

async function persistDraft(row) {
  const edit = state(row), version = edit.version;
  try {
    await localWriteRows([{...snapshot(row), _pending: Boolean(row._pending || version > edit.saved), _syncError: edit.error}]);
    edit.localSaved = Math.max(edit.localSaved, version);
    if (edit.version === version) edit.localError = '';
    return true;
  } catch (error) {
    if (edit.version === version) edit.localError = '手机保存失败，请保持页面打开并重试：' + (error.message || '存储空间不足');
    return false;
  } finally { refreshEntryStatus(row); }
}

function syncStatus(row) {
  const edit = state(row);
  if (edit.localError) return {kind:'error', text:'手机保存失败'};
  if (edit.error || row._syncError) return {kind:'error', text:'同步失败'};
  if (row._pending || edit.pending || edit.version > edit.saved) return {kind:'busy', text:'待同步'};
  return {kind:'ok', text:'已同步'};
}

function save(row) {
  const edit = state(row);
  clearTimeout(edit.timer);
  if (edit.version <= edit.saved) return Promise.resolve(true);
  if (edit.requested === edit.version) return edit.last;
  if (navigator.onLine === false) { refreshEntryStatus(row); return Promise.resolve(false); }
  const version = edit.version;
  edit.requested = version;
  edit.pending++;
  edit.error = '';
  row._syncError = '';
  refreshEntryStatus(row);
  edit.last = enqueue([snapshot(row)]).then(() => {
    edit.saved = Math.max(edit.saved, version);
    if (edit.requested === version) { edit.error = ''; row._syncError = ''; }
    return true;
  }, async error => {
    if (edit.requested === version) edit.requested = -1;
    if (edit.version === version) {
      edit.error = navigator.onLine === false ? '' : (error.message || '连接失败');
      row._syncError = edit.error;
      await persistDraft(row);
    }
    return false;
  }).finally(() => {
    edit.pending--;
    refreshEntryStatus(row);
  });
  return edit.last;
}

function change(row, immediate = false) {
  const edit = state(row);
  edit.version++;
  const values=remote.values(row);
  for(const key of Object.keys(values))if(values[key]!==edit.values[key])edit.fields[key]=edit.version;
  edit.values=values;
  row._dirtyFields=Object.keys(edit.fields);
  row._pending = true;
  row._syncError = ''; edit.error = '';
  const persisted = persistDraft(row);
  clearTimeout(edit.timer);
  if (immediate) return persisted.then(ok => {
    if (ok) void save(row);
    return ok;
  });
  refreshEntryStatus(row);
  if (!composing) edit.timer = setTimeout(() => save(row), 450);
}

function refreshEntryStatus(row) {
  if (page === 'tasks') renderList();
  if (current !== row) return;
  const edit = state(row);
  const status = $('save-state');
  const pendingWrite = edit.pending || edit.version > edit.saved;
  const mobile = !wideScreen?.matches;
  const sync = syncStatus(row);
  status.dataset.tone = sync.kind;
  status.textContent = row.submittedAt ? '待审核' : edit.localError ? '手机保存失败' :
    edit.photoError ? '照片待处理' : edit.localSaved < edit.version ? '正在存到手机…' : edit.error ? '已存手机 · 同步失败' :
      pendingWrite || row._pending ? '已存手机 · 待同步' : '已同步到系统';
  $('save-return').disabled = busy || Boolean(edit.photoError);
  $('save-return').textContent = busy ? '保存中…' : '保存';
  $('camera').disabled = busy;
  $('album').disabled = busy;
  $('photo-count').textContent = row.photos.length ? row.photos.length + ' 张' : mobile ? '未添加' : '';
  const message = edit.localError || edit.error || edit.photoError;
  $('editor-feedback').hidden = !message;
  $('editor-feedback').textContent = message;
  $('photo-feedback').innerHTML = message ?
    '<p class="notice error">' + escapeHtml(message) +
      (remote.conflicts.has(row.id) ? '<button data-action="resolve-conflict" type="button">核对冲突</button>' : edit.error || edit.localError ? '<button data-action="retry-save" type="button">重试保存</button>' :
        '<button data-action="clear-photo-error" type="button">关闭</button>') + '</p>' : '';
}

function setOptions(select, entries, defaultLabel) {
  const selected = select.value;
  select.replaceChildren(new Option(defaultLabel, ''), ...entries.map(([value, label]) => new Option(label, value)));
  if (entries.some(([value]) => value === selected)) select.value = selected;
}

function renderTask(row) {
  const selected = current === row ? ' aria-current="true"' : '';
  const sync = syncStatus(row);
  const result = resultValues.includes(row.result) ? row.result : '';
  const badge = row.returned && !row.submittedAt ?
    '<span class="pill warn">退回重新验货</span>' :
    '<span class="pill" data-judgment="' + result + '">' + (result || '未判定') + '</span>';
  const label = [row.customer, row.returned && !row.submittedAt ? '退回重新验货' : result || '未判定',
    row.po && 'PO ' + row.po, row.sku && '货号 ' + row.sku, row.product, sync.text].filter(Boolean).join('，');
  return '<button type="button" class="task" data-task="' + row.id + '" aria-label="' + escapeHtml(label) + '"' + selected + '>' +
    '<span class="task-main"><span class="row-head"><span>' + escapeHtml(row.customer) + '</span>' + badge + '</span>' +
    '<span class="task-ids"><span><small>PO</small><span>' + escapeHtml(row.po || '—') + '</span></span>' +
    '<span><small>货号</small><span>' + escapeHtml(row.sku || '—') + '</span></span></span>' +
    '<span class="task-foot"><span class="product">' + escapeHtml(row.product) + '</span><span class="task-sync" data-tone="' + sync.kind + '">' + sync.text + '</span></span></span>' +
    icon('next') + '</button>';
}

// Presentation only: keep the desktop/pending renderer and all record contracts intact.
function renderMobileTask(row) {
  const sync = syncStatus(row), result = row.result || '未判定';
  const color = Array.from(row.customer).reduce((hash, char) => (hash * 31 + char.codePointAt(0)) >>> 0, 0) % 4;
  const label = [row.customer, 'PO ' + (row.po || '—'), '货号 ' + (row.sku || '—'), row.product, result, sync.text, row.returned && '退回重新验货'].filter(Boolean).join('，');
  return '<button type="button" class="task mobile-task" data-customer-color="' + color + '" data-task="' + escapeHtml(row.id) + '" aria-label="' + escapeHtml(label) + '"' + (current === row ? ' aria-current="true"' : '') + '>' +
    '<span class="mobile-task-copy"><span class="mobile-customer-row"><strong class="mobile-customer">' + escapeHtml(row.customer) + '</strong><span class="pill" data-judgment="' + escapeHtml(row.result || '') + '">' + escapeHtml(result) + '</span></span>' +
    '<span class="mobile-identifiers"><span><small>PO</small><span>' + escapeHtml(row.po || '—') + '</span></span><span><small>货号</small><span>' + escapeHtml(row.sku || '—') + '</span></span></span>' +
    '<span class="mobile-product-row"><span class="mobile-product">' + icon('product') + '<span>' + escapeHtml(row.product || '—') + '</span></span><span class="task-sync" data-tone="' + sync.kind + '">' + sync.text + '</span></span>' +
    (row.returned ? '<span class="mobile-returned">退回重新验货</span>' : '') + '</span><span class="mobile-task-aside">' + icon('next') + '</span></button>';
}

// User-confirmed handling status; never rewrites the inspection judgment.
const hasInspectionResult = row => Boolean(String(row.result || '').trim());
function matchesTaskFilters(row, keyword, day, customer) {
  const searchText = [row.customer, row.po, row.sku, row.customerPo, row.product, row.remark].join(' ').toLowerCase();
  return (!keyword || searchText.includes(keyword)) && (!day || day === row.start) && (!customer || customer === row.customer);
}

const activeRows = () => rows;

function renderList({ updateOptions = false } = {}) {
  const active = activeRows();
  const available = active.filter(row => !row.submittedAt);
  if (updateOptions) {
    const days = [...new Set(available.map(row => row.start).filter(Boolean))].sort();
    const multipleYears = new Set(days.map(day => day.slice(0, 4))).size > 1;
    setOptions($('day'), days.map(day => [day, multipleYears ? day : dateLabel(day)]), '全部日期');
    setOptions($('customer'), [...new Set(available.map(row => row.customer))].sort((a, b) => a.localeCompare(b, 'zh-CN'))
      .map(customer => [customer, customer]), '全部客户');
  }
  const keyword = $('search').value.trim().toLowerCase();
  $('clear-search').hidden = !$('search').value;
  for (const id of ['day', 'customer']) {
    const select = $(id);
    const trigger = $(id + '-filter');
    const label = select.selectedOptions[0].textContent;
    trigger.querySelector('span').textContent = label;
    trigger.classList.toggle('active', Boolean(select.value));
    trigger.setAttribute('aria-label', (id === 'day' ? '计划验货日期：' : '客户：') + label);
  }
  const filteredRows = available.filter(row => matchesTaskFilters(row, keyword, $('day').value, $('customer').value));
  const done = filteredRows.filter(hasInspectionResult).length;
  $('list-total').textContent = filteredRows.length;
  $('list-todo').textContent = filteredRows.length - done;
  $('list-done').textContent = done;
  all('[data-progress]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.progress === progressFilter)));
  const visible = wideScreen?.matches || progressFilter === 'all' ? filteredRows : filteredRows.filter(row => hasInspectionResult(row) === (progressFilter === 'done'));
  visible.sort((a, b) => {
    if (Boolean(a.start) !== Boolean(b.start)) return a.start ? -1 : 1;
    const date = a.start.localeCompare(b.start);
    return date || a.customer.localeCompare(b.customer, 'zh-CN', { numeric: true, sensitivity: 'base' }) ||
      a.id.localeCompare(b.id);
  });
  const groups = new Map();
  for (const row of visible) {
    if (!groups.has(row.start)) groups.set(row.start, []);
    groups.get(row.start).push(row);
  }
  const multipleYears = new Set(visible.map(row => row.start.slice(0, 4)).filter(Boolean)).size > 1;
  $('task-count').textContent = visible.length + ' 条待办';
  const filtered = Boolean($('day').value || $('customer').value);
  $('list-filter').classList.toggle('active', filtered);
  $('list-filter').setAttribute('aria-label', '筛选：' + $('day').selectedOptions[0].textContent + '，' + $('customer').selectedOptions[0].textContent);
  $('task-list').innerHTML = [...groups].map(([day, group]) =>
    '<div class="section-label"><span>' + (day && multipleYears ? day : dateLabel(day)) + '</span>' + (!wideScreen?.matches ? '<span class="date-count">（' + group.length + '条）</span>' : '') + '</div>' +
    '<div class="rows">' + group.map(row => wideScreen?.matches ? renderTask(row) : renderMobileTask(row)).join('') + '</div>').join('') ||
    '<p class="empty">' + (available.length ? '没有符合条件的验货任务。' : '没有待处理的验货任务。') + '</p>';
  const returned = visible.filter(row => row.returned);
  $('return-notice').innerHTML = returned.length && !seenReturned ?
    '<button class="notice warning return-link" type="button" data-return="' + returned[0].id + '">' +
      icon('alert') + returned.length + ' 笔退回复验 <span class="spacer"></span>查看' + icon('next') + '</button>' : '';
  $('list-notice').innerHTML = wideScreen?.matches && desktopReceipt ? '<p class="notice success"><span>' + escapeHtml(desktopReceipt) + '</span></p>' : '';
  const pending = available.filter(r => syncStatus(r).kind !== 'ok');
  $('sync-summary').hidden = !pending.length;
  $('sync-summary').textContent = pending.length ? pending.length + ' 条未同步到系统 · 点击重试' : '';
}

function renderPending() {
  const pending = activeRows().filter(row => row.submittedAt).sort((a, b) => b.submittedAt.localeCompare(a.submittedAt));
  $('pending-list').innerHTML = pending.length ? '<div class="rows">' + pending.map(renderTask).join('') + '</div>' :
    '<p class="empty">还没有提交记录。</p>';
}

function showPage(name) {
  page = name;
  renderLayout();
}

function renderLayout() {
  const wide = Boolean(wideScreen?.matches);
  const list = page === 'entry' ? entryFrom : page;
  app.classList.toggle('web-layout', wide);
  $('tasks').hidden = wide ? list !== 'tasks' : page !== 'tasks';
  $('pending').hidden = wide ? list !== 'pending' : page !== 'pending';
  $('entry').hidden = page !== 'entry';
  $('web-idle').hidden = !wide || page === 'entry';
  $('photo-actions').hidden = Boolean(current?.submittedAt);
  if (current) refreshEntryStatus(current);
  positionComposer();
}

function positionComposer() {
  const field = wideScreen?.matches && activeField && document.querySelector('[data-open-field="' + activeField + '"]');
  if (field && field.nextElementSibling !== composer) {
    if (field.parentElement.moveBefore) field.parentElement.moveBefore(composer, field.nextSibling);
    else field.after(composer);
  } else if (!field && composer.parentElement !== $('entry')) {
    $('entry').append(composer);
  }
}

function markCurrentTask() {
  for (const button of all('[data-task]')) {
    if (button.dataset.task === current?.id) button.setAttribute('aria-current', 'true');
    else button.removeAttribute('aria-current');
  }
}

function entryNotice(message = '') {
  $('entry-notice').innerHTML = message ? '<p class="notice error" role="alert">' + escapeHtml(message) + '</p>' : '';
}

function releasePhotoUrls() {
  for (const url of photoUrls.values()) URL.revokeObjectURL(url);
  photoUrls.clear();
}

function photoUrl(photo) {
  if (photo.url && !photo.blob) return photo.url;
  if (!photoUrls.has(photo.id)) photoUrls.set(photo.id, URL.createObjectURL(photo.blob));
  return photoUrls.get(photo.id);
}

function renderPhotos(row) {
  $('photo-list').innerHTML = row.photos.map(photo =>
    '<div class="photo-row"><button class="photo-open" type="button" data-photo="' + photo.id + '">' +
      '<span class="thumb"><img src="' + escapeHtml(photoUrl(photo)) + '" alt=""></span>' +
      '<span class="photo-text">' + escapeHtml(photo.name) + '<small>查看照片</small></span></button>' +
      (row.submittedAt ? '' : '<button class="icon-button" type="button" data-remove-photo="' + photo.id +
        '" aria-label="移除 ' + escapeHtml(photo.name) + '">' + icon('close') + '</button>') + '</div>').join('');
  for (const img of $('photo-list').querySelectorAll('img')) {
    img.addEventListener('error', () => { img.parentElement.innerHTML = icon('images'); }, { once: true });
  }
}

function setResult(value) {
  for (const button of all('[data-result]')) button.setAttribute('aria-pressed', String(button.dataset.result === value));
}

function renderFieldPreview(row, id) {
  const note = document.querySelector('[data-note="' + id + '"]');
  if (!composingNotes.has(note) && note.value !== (row[id] || '')) note.value = row[id] || '';
  const preview = $(id);
  preview.textContent = row[id] || (row.submittedAt ? '未填写' : '点击填写');
  preview.dataset.empty = String(!row[id]);
}

function setEntryReadOnly(readOnly) {
  for (const note of all('[data-note]')) note.readOnly = readOnly;
  for (const button of all('[data-open-field]')) button.disabled = readOnly;
  $('sample-quantity').disabled = readOnly;
  $('inspector').disabled = readOnly;
  for (const button of all('[data-result]')) button.disabled = readOnly;
}

function renderEntry(row, from) {
  if (page === 'tasks') listPosition = taskScroll.scrollTop;
  if (current && current !== row) releasePhotoUrls();
  entryFrom = from;
  keyboardSession = null;
  current = row;
  const readonly = Boolean(row.submittedAt);
  $('entry-title').textContent = readonly ? '待审核详情' : '验货';
  $('back').lastChild.textContent = readonly ? '待审核' : '验货台';
  $('who').textContent = row.customer;
  $('entry-product').textContent = row.product || '';
  $('entry-product').hidden = !row.product;
  $('po').textContent = row.po ? 'PO ' + row.po : '';
  $('sku').textContent = ['货号 ' + row.sku, row.batch && '批次 ' + row.batch].filter(Boolean).join(' · ');
  $('composer-order').textContent = row.po + ' · ' + row.sku;
  $('plan').textContent = planDate(row) ? '计划 ' + planDate(row) : '未排日期';
  $('return-reason').hidden = !row.returned || readonly;
  $('return-copy').textContent = row.returned;
  $('submitted-info').hidden = !readonly;
  $('submitted-info').textContent = '已进入待审核';
  $('sample-quantity').value = row.sampleQuantity ?? '';
  $('inspector').value = row.inspector ?? '';
  for (const id of fieldIds) renderFieldPreview(row, id);
  setEntryReadOnly(readonly);
  setResult(row.result);
  activeField = '';
  composing = false;
  editorSelections.clear();
  editorTrigger = null;
  entryNotice();
  showPage('entry');
  markCurrentTask();
  syncEditing();
  renderPhotos(row);
  refreshEntryStatus(row);
  entryScroll.scrollTop = 0;
}

function syncEditing() {
  const editing = page === 'entry' && Boolean(activeField);
  app.classList.toggle('editing', editing);
  composer.hidden = !editing || !wideScreen?.matches;
  updateSaveDock();
  positionComposer();
  for (const button of all('[data-focus]')) {
    button.setAttribute('aria-pressed', String(button.dataset.focus === activeField));
  }
}

// Some Android keyboards dismiss without blurring the field. Keep the initial
// visible height across field switches so recovery can be detected on resize.
let keyboardSession = null;
function updateSaveDock() {
  $('dock').hidden = Boolean(current?.submittedAt || (!wideScreen?.matches && keyboardSession));
}

function beginPhoneInput() {
  if (wideScreen?.matches || !current || current.submittedAt) return;
  if (!keyboardSession) {
    const viewport = window.visualViewport;
    keyboardSession = {height: viewport?.height ?? window.innerHeight, reduced: false};
  }
  updateSaveDock();
}

function reconcileKeyboard(height, blurred = false) {
  if (!keyboardSession) return;
  const reduction = keyboardSession.height - height;
  if (reduction > 90) keyboardSession.reduced = true;
  const recovered = keyboardSession.rotatedWhileOpen ? reduction < -90 : keyboardSession.reduced && reduction < 60;
  if (recovered || (blurred && !keyboardSession.reduced && !keyboardSession.rotatedWhileOpen)) {
    keyboardSession = null;
    updateSaveDock();
  }
}

let revealOnFocus = false;
function syncViewport() {
  const viewport = window.visualViewport;
  const height = Math.round(viewport?.height ?? window.innerHeight);
  const width = Math.round(viewport?.width ?? window.innerWidth);
  const previousHeight = parseInt(app.style.getPropertyValue('--viewport-height'), 10);
  const rotated = viewportWidth && viewportWidth !== width;
  if (rotated && keyboardSession) {
    // Rotation changes the baseline. If an input is still active, use a
    // subsequent height gain to detect dismissal in the new orientation.
    if (entryScroll.contains(document.activeElement)) {
      keyboardSession = {height, rotatedWhileOpen: keyboardSession.reduced, reduced: false};
    } else keyboardSession = null;
    updateSaveDock();
  }
  if (viewportWidth !== width) {
    viewportWidth = width;
    unoccludedHeight = height;
  }
  if (document.activeElement !== editor) unoccludedHeight = Math.max(height, unoccludedHeight);
  app.style.setProperty('--viewport-height', height + 'px');
  app.style.setProperty('--viewport-top', Math.round(viewport?.pageTop ?? viewport?.offsetTop ?? 0) + 'px');
  app.classList.toggle('short-view', height < 320);
  app.classList.toggle('keyboard-visible', height < unoccludedHeight - 100);
  const focusedInput = document.activeElement?.matches('[data-note], #inspector, #sample-quantity');
  if (!rotated && !keyboardSession && focusedInput && !wideScreen?.matches && previousHeight - height > 90) {
    // Tapping a still-focused field can reopen the keyboard without a focus event.
    keyboardSession = {height: previousHeight, reduced: true};
    updateSaveDock();
  }
  reconcileKeyboard(height);
  // Check the current focus after opening; closing the keyboard should not reposition the form.
  if (height < previousHeight || (revealOnFocus && height === previousHeight)) revealFocusedField();
  revealOnFocus = false;
}

function revealFocusedField() {
  const input = document.activeElement;
  if (wideScreen?.matches || page !== 'entry' || !entryScroll.contains(input) ||
      !input.matches('[data-note], #inspector, #sample-quantity')) return;

  const area = entryScroll.getBoundingClientRect();
  if (!area.height) return;
  const label = input.closest('label').getBoundingClientRect();
  const margin = 8;
  const available = area.height - 2 * margin;
  const target = label.height <= available ? label : input.getBoundingClientRect();
  const top = area.top + margin;
  const bottom = area.bottom - margin;
  if (target.top < top) entryScroll.scrollTop += target.top - top;
  else if (target.bottom > bottom) entryScroll.scrollTop += Math.min(target.top - top, target.bottom - bottom);
}

function clearEditing(restoreFocus = true) {
  if (!activeField) return;
  editor.blur();
  captureEditor();
  const row = current;
  composing = false;
  activeField = '';
  $('editor-feedback').hidden = true;
  syncEditing();
  if (row) void save(row);
  if (restoreFocus && editorTrigger?.isConnected) editorTrigger.focus({ preventScroll: true });
  editorTrigger = null;
}

async function backFromEntry() {
  if (!current || busy) return;
  if (!$('sample-quantity').reportValidity()) return;
  clearEditing(false);
  const row = current;
  if (state(row).photoError) { entryNotice('请先处理照片提示。'); return; }
  busy = true;
  setEntryReadOnly(true);
  refreshEntryStatus(row);
  try {
    if (!await persistDraft(row)) { entryNotice(state(row).localError); return; }
    // Leaving the form depends on a committed local transaction, never the network.
    if (wideScreen?.matches) desktopReceipt = row.po + ' · 已保存到手机';
    current = null;
    releasePhotoUrls();
    showPage('tasks');
    renderList();
    taskScroll.scrollTop = listPosition;
    if (!row.submittedAt) void save(row);
  } finally {
    busy = false;
    if (current === row) { setEntryReadOnly(false); refreshEntryStatus(row); }
  }
}

async function openPending() {
  if (busy || openingTask) return;
  if (current && page === 'entry') {
    await backFromEntry();
    if (current) return;
  }
  if (page === 'tasks') listPosition = taskScroll.scrollTop;
  renderPending();
  showPage('pending');
}

function showSheet(title, content) {
  dialogTrigger = document.activeElement;
  photoCanClose = null;
  sheet.classList.remove('filter-sheet', 'mobile-filters-sheet', 'photo-markup-sheet');
  $('sheet-title').textContent = title;
  $('sheet-content').innerHTML = content;
  if (!sheet.open) sheet.showModal();
}

function closeSheet() {
  if (sheet.open && (!photoCanClose || photoCanClose())) sheet.close();
}

function showFilter(id) {
  const select = $(id);
  const trigger = $(id + '-filter');
  let draft = select.value;
  $('search').blur();
  showSheet(id === 'day' ? '计划验货日期' : '选择客户',
    '<div class="filter-options" role="group" aria-label="筛选选项">' +
    [...select.options].map((option, index) =>
      '<button type="button" class="filter-option" data-option="' + index +
      '" aria-pressed="' + (option.value === draft) + '">' + escapeHtml(option.textContent) + '</button>'
    ).join('') + '</div><button type="button" class="primary filter-apply">确认筛选</button>' +
    '<button type="button" class="filter-reset">清除此项筛选</button>');
  dialogTrigger = trigger;
  sheet.classList.add('filter-sheet');
  const options = [...$('sheet-content').querySelectorAll('[data-option]')];
  const update = () => options.forEach(button => {
    const option = select.options[Number(button.dataset.option)];
    const selected = option.value === draft;
    button.setAttribute('aria-pressed', String(selected));
    button.textContent = option.textContent + (selected ? ' ✓' : '');
  });
  options.forEach(button => button.onclick = () => {
    draft = select.options[Number(button.dataset.option)].value;
    update();
  });
  $('sheet-content').querySelector('.filter-reset').onclick = () => { draft = ''; update(); };
  $('sheet-content').querySelector('.filter-apply').onclick = () => {
    select.value = draft;
    renderList();
    taskScroll.scrollTop = 0;
    closeSheet();
  };
  update();
  options.find(button => button.getAttribute('aria-pressed') === 'true')?.focus();
}

function showMobileFilters() {
  const draft = {day:$('day').value, customer:$('customer').value};
  const optionSets = Object.fromEntries(['day','customer'].map(id => [id, [...$(id).options].map(option => ({value:option.value, label:option.textContent}))]));
  const labels = {day:'验货日期', customer:'客户'};
  const icons = {
    day:'<svg aria-hidden="true" viewBox="0 0 24 24"><rect x="4" y="5" width="16" height="16" rx="3"/><path d="M8 3v4m8-4v4M4 10h16"/></svg>',
    customer:'<svg aria-hidden="true" viewBox="0 0 24 24"><circle cx="12" cy="7" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2Z"/></svg>'
  };
  const selectedLabel = id => optionSets[id].find(option => option.value === draft[id])?.label || '';
  const resultCount = () => rows.filter(row => !row.submittedAt && matchesTaskFilters(row, $('search').value.trim().toLowerCase(), draft.day, draft.customer) && (progressFilter === 'all' || hasInspectionResult(row) === (progressFilter === 'done'))).length;
  let customerQuery = '';
  $('search').blur();
  showSheet('筛选', '');
  dialogTrigger = $('list-filter');
  sheet.classList.add('mobile-filters-sheet');
  const content = $('sheet-content');
  const viewport = window.visualViewport;
  const fitViewport = () => {
    sheet.style.setProperty('--filter-visible-height', (viewport?.height ?? window.innerHeight) + 'px');
    sheet.style.setProperty('--filter-bottom', Math.max(0, window.innerHeight - (viewport?.height ?? window.innerHeight) - (viewport?.offsetTop ?? 0)) + 'px');
  };
  let filterResizeTimer;
  const scheduleFit = () => {
    clearTimeout(filterResizeTimer);
    filterResizeTimer = setTimeout(fitViewport, 100);
  };
  fitViewport();
  viewport?.addEventListener('resize', scheduleFit);
  viewport?.addEventListener('scroll', scheduleFit);
  window.addEventListener('resize', scheduleFit);
  sheet.addEventListener('close', () => {
    clearTimeout(filterResizeTimer);
    viewport?.removeEventListener('resize', scheduleFit);
    viewport?.removeEventListener('scroll', scheduleFit);
    window.removeEventListener('resize', scheduleFit);
    sheet.style.removeProperty('--filter-visible-height');
    sheet.style.removeProperty('--filter-bottom');
    sheet.classList.remove('mobile-filters-sheet');
  }, {once:true});

  function renderMain(returnFrom) {
    document.activeElement?.blur();
    $('sheet-title').textContent = '筛选';
    content.innerHTML = '<div class="mobile-filter-page'+(returnFrom?' filter-page-back':'')+'"><header class="mobile-filter-heading"><h2>筛选</h2><button type="button" class="mobile-filter-close" data-filter-close aria-label="关闭筛选">'+icon('close')+'</button></header><div class="mobile-filter-main"><div class="mobile-filter-settings">'+['day','customer'].map(id => '<button type="button" class="mobile-filter-setting" data-filter-page="'+id+'">'+icons[id]+'<span class="filter-setting-label">'+labels[id]+'</span><span class="filter-setting-value">'+escapeHtml(selectedLabel(id))+'</span>'+icon('next')+'</button>').join('')+'</div></div><footer class="mobile-filter-actions"><button type="button" data-filter-reset>重置</button><button type="button" data-filter-apply>查看 '+resultCount()+' 条结果</button></footer></div>';
    content.querySelector('[data-filter-close]').onclick = closeSheet;
    content.querySelectorAll('[data-filter-page]').forEach(button => button.onclick = () => renderChoices(button.dataset.filterPage));
    content.querySelector('[data-filter-reset]').onclick = () => { draft.day=''; draft.customer=''; customerQuery=''; renderMain(); content.querySelector('[data-filter-reset]').focus({preventScroll:true}); };
    content.querySelector('[data-filter-apply]').onclick = () => {
      for (const id of ['day','customer']) {
        if (![...$(id).options].some(option => option.value === draft[id])) $(id).add(new Option(selectedLabel(id), draft[id]));
        $(id).value = draft[id];
      }
      renderList(); taskScroll.scrollTop=0; closeSheet();
    };
    if (returnFrom) content.querySelector('[data-filter-page="'+returnFrom+'"]').focus({preventScroll:true});
  }

  function renderChoices(id) {
    $('sheet-title').textContent = labels[id];
    content.innerHTML = '<div class="mobile-filter-page filter-page-forward"><header class="mobile-filter-subheading"><button type="button" data-filter-back>'+icon('back')+'筛选</button><h2>'+labels[id]+'</h2><button type="button" class="mobile-filter-close" data-filter-close aria-label="关闭筛选">'+icon('close')+'</button></header>'+(id==='customer'?'<div class="mobile-filter-search">'+icon('search')+'<input id="filter-customer-search" type="search" placeholder="搜索客户" aria-label="搜索筛选客户" autocomplete="off"></div>':'')+'<div class="mobile-filter-options-scroll"><div class="mobile-filter-options" role="group" aria-label="'+labels[id]+'"></div><p id="filter-customer-empty" hidden>没有匹配的客户</p></div></div>';
    content.querySelector('[data-filter-back]').onclick = () => renderMain(id);
    content.querySelector('[data-filter-close]').onclick = closeSheet;
    const renderOptions = () => {
      const keyword = id === 'customer' ? customerQuery.trim().toLowerCase() : '';
      const options = optionSets[id].map((option, index) => ({...option,index})).filter(option => !keyword || !option.value || option.label.toLowerCase().includes(keyword));
      content.querySelector('.mobile-filter-options').innerHTML = options.map(option => '<button type="button" data-filter="'+id+'" data-choice="'+option.index+'" aria-pressed="'+(option.value===draft[id])+'"><span>'+escapeHtml(option.label)+'</span>'+(option.value===draft[id]?icon('check'):'')+'</button>').join('');
      content.querySelectorAll('[data-choice]').forEach(button => button.onclick = () => { draft[id]=optionSets[id][Number(button.dataset.choice)].value; renderMain(id); });
      $('filter-customer-empty').hidden = !keyword || options.some(option => option.value);
    };
    if (id === 'customer') {
      $('filter-customer-search').value = customerQuery;
      $('filter-customer-search').oninput = () => { customerQuery=$('filter-customer-search').value; renderOptions(); };
    }
    renderOptions();
    content.querySelector('[data-filter-back]').focus({preventScroll:true});
  }
  renderMain();
  content.querySelector('[data-filter-page]').focus({preventScroll:true});
}

function showPhoto(photo) {
  const row=current,shapes=window.QcPhotoShapes;
  const editable=!row.submittedAt&&shapes;
  const initial=photo.annotations||[];
  let marks=initial,tool='browse',drawing=null,loaded=false,savingMarks=false;
  showSheet(photo.name,(editable?`<div class="photo-markup-tools" role="group" aria-label="照片标记">${shapes.toolButtons}</div>`:'')+
    '<p class="photo-markup-status" role="status" hidden></p><div class="photo-markup-stage"><div class="photo-markup-image"><img class="photo-preview" alt="验货照片"><svg aria-hidden="true"></svg></div></div>');
  sheet.classList.add('photo-markup-sheet');
  const content=$('sheet-content'),stage=content.querySelector('.photo-markup-stage'),frame=stage.firstElementChild;
  const image=frame.querySelector('img'),layer=frame.querySelector('svg');
  const saveButton=content.querySelector('[data-mark-save]'),undo=content.querySelector('[data-mark-undo]');
  const tools=content.querySelectorAll('[data-mark-tool]');
  const status=content.querySelector('[role=status]');
  const dirty=()=>editable&&!shapes.equal(marks,initial);
  const message=text=>{status.textContent=text;status.hidden=!text;};
  const paint=()=>shapes?.paint(layer,image.naturalWidth,image.naturalHeight,drawing?[...marks,drawing.mark]:marks);
  function fitPhoto(){
    if(!loaded||!stage.clientWidth||!stage.clientHeight)return;
    const scale=Math.min(1,Math.max(1,stage.clientWidth-32)/image.naturalWidth,Math.max(1,stage.clientHeight-32)/image.naturalHeight);
    frame.style.width=image.naturalWidth*scale+'px';
    frame.style.height=image.naturalHeight*scale+'px';
  }
  const observer=window.ResizeObserver?new ResizeObserver(fitPhoto):null;
  observer?.observe(stage);
  sheet.addEventListener('close',()=>observer?.disconnect(),{once:true});
  function controls(){
    if(!editable)return;
    frame.classList.toggle('is-marking',tool!=='browse'&&loaded&&!savingMarks);
    for(const button of tools){
      button.disabled=!loaded||savingMarks;
      button.setAttribute('aria-pressed',String(button.dataset.markTool===tool));
    }
    undo.disabled=!loaded||savingMarks||!marks.length;
    saveButton.disabled=!loaded||savingMarks||!dirty();
  }
  photoCanClose=()=>!savingMarks&&(!dirty()||window.confirm('放弃当前未保存的照片标记？'));
  image.onload=()=>{
    loaded=true;layer.setAttribute('viewBox',`0 0 ${image.naturalWidth} ${image.naturalHeight}`);
    fitPhoto();paint();controls();
  };
  image.onerror=()=>{loaded=false;frame.hidden=true;message('无法加载照片，请联网后重试。');controls();};
  image.draggable=false;
  image.src=photoUrl(photo);
  controls();
  if(!editable)return;
  for(const button of tools)button.onclick=()=>{tool=button.dataset.markTool;controls();};
  undo.onclick=()=>{marks=marks.slice(0,-1);message('');paint();controls();};
  const fraction=value=>Math.round(Math.max(0,Math.min(1,value))*1e6)/1e6;
  const point=(event,bounds)=>[
    fraction((event.clientX-bounds.left)/bounds.width),fraction((event.clientY-bounds.top)/bounds.height),
  ];
  frame.addEventListener('pointerdown',event=>{
    if(!loaded||savingMarks||tool==='browse'||event.button!==0||drawing)return;
    if(marks.length>=40){message('每张照片最多 40 笔标记');return;}
    const bounds=image.getBoundingClientRect();
    if(!bounds.width||!bounds.height)return;
    const [x,y]=point(event,bounds);
    event.preventDefault();
    drawing={id:event.pointerId,bounds,mark:{type:tool,x1:x,y1:y,x2:x,y2:y}};
    frame.setPointerCapture?.(event.pointerId);
  });
  function move(event){
    if(!drawing||drawing.id!==event.pointerId)return;
    const [x,y]=point(event,drawing.bounds);
    Object.assign(drawing.mark,{x2:x,y2:y});paint();
  }
  frame.addEventListener('pointermove',move);
  for(const name of ['pointerup','pointercancel','lostpointercapture'])frame.addEventListener(name,event=>{
    if(!drawing||drawing.id!==event.pointerId)return;
    if(name==='pointerup'){
      move(event);
      const {mark,bounds}=drawing;
      const dx=(mark.x2-mark.x1)*bounds.width,dy=(mark.y2-mark.y1)*bounds.height;
      if(mark.type==='circle'?Math.abs(dx)>=4&&Math.abs(dy)>=4:Math.hypot(dx,dy)>=4)marks=[...marks,mark];
    }
    drawing=null;paint();controls();
  });
  saveButton.onclick=async()=>{
    if(savingMarks||!dirty())return;
    const target=row.photos.find(item=>item.id===photo.id||item.remoteId&&item.remoteId===photo.remoteId);
    if(!target||row.submittedAt){message('照片已移除或任务已提交，请核对当前记录。');return;}
    if(!shapes.equal(target.annotations,initial)&&!shapes.equal(target.annotations,marks)){
      message('照片标记已更新，请关闭后重新打开核对。');return;
    }
    savingMarks=true;message('正在保存到手机…');controls();
    target.annotations=marks;target._annotationsPending=true;
    const stored=await change(row,true);
    savingMarks=false;
    if(stored){photoCanClose=null;closeSheet();}
    else{message(state(row).localError);controls();}
  };
}

function showInfo() {
  const row = current;
  const data = [['客户', row.customer], ['客户 PO', row.customerPo], ['PO', row.po],
    ['货号', row.sku], ['产品名称', row.product], ['计划验货日期', planDate(row)],
    ['批次', row.batch], ['数量', row.quantity], ['装箱', row.packing], ['箱数', row.cartons]];
  showSheet('订单资料', '<dl class="facts">' + data.map(([label, value]) =>
    '<div><dt>' + escapeHtml(label) + '</dt><dd>' + escapeHtml(value) + '</dd></div>').join('') + '</dl>');
}

function captureEditor() {
  if (!activeField || !current || current.submittedAt || composing) return;
  const field = activeField;
  editorSelections.set(field, [editor.selectionStart, editor.selectionEnd]);
  if (current[field] === editor.value) return;
  current[field] = editor.value;
  current.changedAt = new Date().toISOString();
  renderFieldPreview(current, field);
  change(current);
}

editor.addEventListener('compositionstart', () => {
  composing = true;
  if (current) clearTimeout(state(current).timer);
});
editor.addEventListener('compositionend', () => {
  composing = false;
  captureEditor();
  if (!current) return;
  const row = current;
  const edit = state(row);
  clearTimeout(edit.timer);
  edit.timer = setTimeout(() => save(row), 450);
});
editor.addEventListener('input', captureEditor);
editor.addEventListener('blur', () => {
  composing = false;
  captureEditor();
  if (current && activeField) void save(current);
});

function focusField(id, trigger) {
  if (!wideScreen?.matches || !fieldIds.includes(id) || !current || current.submittedAt || busy) return;
  if (composing && id !== activeField) {
    $('editor-feedback').hidden = false;
    $('editor-feedback').textContent = '请先确认键盘上的候选字。';
    return;
  }
  if (id === activeField) {
    editor.focus({ preventScroll: true });
    return;
  }
  if (!activeField) editorTrigger = trigger;
  captureEditor();
  activeField = id;
  $('editor-label').textContent = fieldLabels[id];
  editor.value = current[id] ?? '';
  editor.placeholder = '输入' + fieldLabels[id];
  refreshEntryStatus(current);
  syncEditing();
  const selection = editorSelections.get(id) ?? [editor.value.length, editor.value.length];
  editor.focus({ preventScroll: !wideScreen?.matches });
  editor.setSelectionRange(...selection);
}

$('keyboard-bar').addEventListener('mousedown', event => {
  if (event.target.closest('button')) event.preventDefault();
});
$('hide-keyboard').onclick = () => clearEditing();
$('back').onclick = backFromEntry;
$('pending-back').onclick = () => {
  showPage('tasks');
  renderList();
  taskScroll.scrollTop = listPosition;
};
$('info').onclick = showInfo;
$('sheet-close').onclick = closeSheet;
sheet.addEventListener('click',event=>{
  if(sheet.classList.contains('photo-markup-sheet')&&
      (event.target===sheet||event.target=== $('sheet-content')||event.target.matches('.photo-markup-stage')))closeSheet();
});
sheet.addEventListener('cancel',event=>{if(photoCanClose&&!photoCanClose())event.preventDefault();});
sheet.addEventListener('close', () => {photoCanClose=null;dialogTrigger?.focus({ preventScroll: true });});
$('search').addEventListener('input', () => renderList());
$('clear-search').onclick = () => {
  $('search').value = '';
  renderList();
  $('search').focus({ preventScroll: true });
};
$('list-filter').onclick = showMobileFilters;
all('[data-progress]').forEach(button => button.onclick = () => {
  progressFilter = button.dataset.progress;
  renderList();
  taskScroll.scrollTop = 0;
});
for (const id of ['day', 'customer']) $(id + '-filter').onclick = () => showFilter(id);
$('day').onchange = $('customer').onchange = () => renderList();
// Field switches can happen while the keyboard stays open, without a viewport resize.
function scheduleFieldReveal() {
  revealOnFocus = true;
  scheduleViewportUpdate();
}

for (const field of [...all('[data-note]'), $('sample-quantity'), $('inspector')]) {
  const key = field.dataset.note || (field.id === 'inspector' ? 'inspector' : 'sampleQuantity');
  function captureInput(event) {
    if (!current || current.submittedAt || busy || event.isComposing || composingNotes.has(field) ||
        !field.validity.valid || (current[key] ?? '') === field.value) return;
    current[key] = field.value;
    current.changedAt = new Date().toISOString();
    change(current);
  }
  field.addEventListener('compositionstart', () => composingNotes.add(field));
  function commitInput(event) {
    composingNotes.delete(field);
    captureInput(event);
  }
  field.addEventListener('compositionend', commitInput);
  field.addEventListener('input', captureInput);
  field.addEventListener('focus', () => {
    beginPhoneInput();
    scheduleFieldReveal();
  });
  field.addEventListener('click', () => {
    if (document.activeElement === field) beginPhoneInput();
  });
  field.addEventListener('blur', event => {
    reconcileKeyboard(window.visualViewport?.height ?? window.innerHeight, true);
    commitInput(event);
    if (current && !current.submittedAt) void save(current);
  });
}

function newPhotoId() {
  return Array.from(crypto.getRandomValues(new Uint8Array(12)), part => part.toString(16).padStart(2, '0')).join('');
}

async function addPhotos(event) {
  const input = event.currentTarget;
  const files = [...input.files];
  input.value = '';
  const row = current;
  if (!files.length || !row || row.submittedAt || busy) return;
  const edit = state(row);
  edit.photoError = '';
  const invalid = files.find(file => !file.size || file.size > maxPhotoBytes ||
    !(file.type.startsWith('image/') || /\.(heic|heif|jpg|jpeg|png|webp|avif)$/i.test(file.name)));
  const total = [...row.photos.map(photo => photo.blob).filter(Boolean), ...files].reduce((sum, file) => sum + file.size, 0);
  if (invalid || row.photos.length + files.length > 50 || total > 100 * 1024 * 1024) {
    edit.photoError = invalid ? invalid.name + ' 无法添加，请选择 10 MB 以内的照片。' : '一笔任务最多 50 张、100 MB。';
    refreshEntryStatus(row);
    return;
  }
  row.photos.push(...files.map(file => ({ id: newPhotoId(), name: file.name || '验货照片', blob: file })));
  row.changedAt = new Date().toISOString();
  renderPhotos(row);
  await change(row, true);
}

$('camera').onchange = $('album').onchange = addPhotos;

$('save-return').onclick = () => {
  if (!$('dock').hidden) void backFromEntry();
};

app.addEventListener('click', event => {
  const button = event.target.closest('button');
  if (!button || button.disabled) return;
  const { task, result, focus, openField, photo, removePhoto, return: returnId, action } = button.dataset;
  if ((task || returnId) && !busy) {
    const row = rows.find(item => item.id === (task || returnId));
    if (row) void openTask(row);
  }
  if (result && current && !current.submittedAt && !busy) {
    current.result = result;
    current.changedAt = new Date().toISOString();
    setResult(result);
    entryNotice();
    change(current, true);
  }
  if (focus) focusField(focus);
  if (openField) focusField(openField, button);
  if (photo && current && !busy) {
    const selected = current.photos.find(item => item.id === photo);
    if (selected) showPhoto(selected);
  }
  if (removePhoto && current && !current.submittedAt && !busy) {
    showSheet('移除这张照片？', '<div class="sheet-actions"><button type="button" class="secondary" data-action="cancel">取消</button>' +
      '<button type="button" class="secondary danger" data-action="remove-photo" data-id="' + removePhoto + '">移除</button></div>');
  }
  if (action === 'cancel') closeSheet();
  if (action === 'open-pending') openPending();
  if (action === 'retry-save' && current) { const row=current; void persistDraft(row).then(ok=>{if(ok)void save(row);}); }
  if (action === 'clear-photo-error' && current) {
    state(current).photoError = '';
    refreshEntryStatus(current);
    entryNotice();
  }
  if (action === 'remove-photo' && current && !current.submittedAt && !busy) {
    const id = button.dataset.id;
    const url = photoUrls.get(id);
    if (url) URL.revokeObjectURL(url);
    photoUrls.delete(id);
    current.photos = current.photos.filter(item => item.id !== id);
    current.changedAt = new Date().toISOString();
    closeSheet();
    renderPhotos(current);
    change(current, true);
  }
});

async function openTask(row) {
  if (openingTask || current === row) return;
  const from = page === 'entry' ? entryFrom : page;
  if (current) {
    openingTask = true;
    try {
      await backFromEntry();
      if (current) return;
    } finally {
      openingTask = false;
    }
  }
  if (navigator.onLine !== false && !row._pending && state(row).version <= state(row).saved) {
    openingTask=true;
    try { const latest=remote.convert(await remote.api('/sheet/entries/'+encodeURIComponent(row.id))); Object.assign(row,latest);row._photoBase=row.photos.map(p=>p.id);state(row).values=remote.values(row);remote.remember(row); }
    catch(error) { $('snapshot-notice').textContent='暂用手机记录：'+error.message+'；填写先保存在手机，联网后再核对同步。'; }
    finally { openingTask=false; }
  }
  if (row.returned) seenReturned = true;
  renderEntry(row, from);
}

wideScreen?.addEventListener('change', () => {
  renderList();
  const wasEditing = document.activeElement === editor;
  renderLayout();
  if (current) for (const id of fieldIds) renderFieldPreview(current, id);
  syncEditing();
  if (wasEditing && wideScreen?.matches) editor.focus({ preventScroll: true });
  else if (!wideScreen?.matches && activeField) clearEditing(false);
});
let viewportTimer;
function scheduleViewportUpdate() {
  // Remember even a brief keyboard resize before the debounced layout pass.
  const viewport = window.visualViewport;
  if (keyboardSession && Math.round(viewport?.width ?? window.innerWidth) === viewportWidth &&
      keyboardSession.height - (viewport?.height ?? window.innerHeight) > 90) keyboardSession.reduced = true;
  // Native focus scrolling runs throughout the keyboard animation; fit the shell once it settles.
  clearTimeout(viewportTimer);
  viewportTimer = setTimeout(syncViewport, 100);
}
window.addEventListener('resize', scheduleViewportUpdate);
window.visualViewport?.addEventListener('resize', scheduleViewportUpdate);
window.visualViewport?.addEventListener('scroll', scheduleViewportUpdate);
window.addEventListener('beforeunload', event => {
  if ([...writeState.values()].some(s=>s.localError || s.localSaved < s.version)) { event.preventDefault(); event.returnValue=''; }
});

remote.onAck = async (sent, saved, photoMap) => {
  for(const queued of queuedSnapshots)if(queued.id===sent.id&&queued._v>sent._v)Object.assign(queued,remote.rebaseDraft(queued,sent,saved,photoMap));
  const row = rows.find(r => r.id === sent.id);
  if (!row) return;
  const edit=state(row);
  const photosChanged = row.photos.length !== saved.photos.length || row.photos.some((photo,index) => {
    const acknowledged = saved.photos[index];
    return photo.id !== acknowledged.id || photo.url !== acknowledged.url || photo.name !== acknowledged.name;
  });
  if(edit.version>sent._v){
    const rebased=remote.rebaseDraft(snapshot(row),sent,saved,photoMap);
    Object.assign(row,rebased);
    for(const key of Object.keys(edit.fields))if(!rebased._dirtyFields.includes(key))delete edit.fields[key];
  }
  row.revision = saved.revision;
  row._photoBase = saved.photos.map(p => p.id);
  row.photos.forEach(p => { if (photoMap?.has(p.id)) p.remoteId = photoMap.get(p.id); });
  if (state(row).version === sent._v) {
    Object.assign(row, saved);
    edit.fields={};
    if (current === row) {
      if (photosChanged) renderPhotos(row);
      for (const id of fieldIds) renderFieldPreview(row,id);
    }
  }
  edit.values=remote.values(row);
  // Persist the rebased newer draft as well, so closing the page during a slow
  // acknowledgement retains both intent and the correct field baselines.
  if(edit.version>sent._v)await localWriteRows([snapshot(row)]);
};

async function refreshLive() {
  if (navigator.onLine === false || busy || document.hidden || openingTask || photoCanClose || [...writeState.values()].some(s => s.pending || s.version > s.saved) || activeField || current && document.activeElement?.closest('#entry')) return;
  try {
    const data = await remote.api('/sheet/entries');
    if (busy || openingTask || photoCanClose || activeField || current && document.activeElement?.closest('#entry') || [...writeState.values()].some(s=>s.pending || s.version>s.saved)) return;
    const latest = data.items.map(remote.convert);
    rows = remote.mergeCache(latest, rows);
    await localWriteRows(rows);
    $('snapshot-notice').textContent = '';
    rows.forEach(remote.remember);
    rows.forEach(row=>{if(!row._pending)state(row).values=remote.values(row);});
    renderList({updateOptions:true});
    if (current) {
      const replacement = rows.find(r => r.id === current.id);
      if (replacement) { const top=entryScroll.scrollTop; renderEntry(replacement,entryFrom); entryScroll.scrollTop=top; }
      else { current=null; showPage('tasks'); }
    }
  } catch (error) { $('snapshot-notice').textContent = '暂未刷新：' + error.message; }
}

app.addEventListener('click', async event => {
  const action = event.target.closest('button')?.dataset.action;
  if (action === 'resolve-conflict' && current) {
    const conflict=remote.conflicts.get(current.id);
    if(!conflict)return;
    const labels={...fieldLabels,improvement:'改善措施',result:'验货结果',sampleQuantity:'抽查数量',inspector:'检验人员'};
    const notes=conflict.keys.map(k=>'<section class="notice"><strong>'+escapeHtml(labels[k])+'</strong><p>系统：'+escapeHtml(conflict.latest[k]||'空白')+'</p><p>我的填写：'+escapeHtml(current[k]||'空白')+'</p></section>');
    for(const {name,server} of conflict.photos)notes.push('<section class="notice"><strong>'+escapeHtml(name)+'</strong><p>'+(server?'这张照片的标记已被其他设备修改。':'这张照片已从系统移除。')+'</p></section>');
    const hasRemoved=conflict.photos.some(photo=>!photo.server);
    showSheet('核对同时修改的内容',notes.join('')+'<div class="sheet-actions"><button class="secondary" data-action="conflict-server">采用系统内容</button><button class="primary" data-action="conflict-mine" '+(hasRemoved?'disabled':'')+'>保留手机内容</button></div>');
  }
  if (['conflict-server','conflict-mine'].includes(action) && current) {
    await remote.resolve(current, action==='conflict-server'?'server':'mine'); closeSheet();
    renderPhotos(current);
    for(const id of fieldIds)renderFieldPreview(current,id);
    setResult(current.result);$('sample-quantity').value=current.sampleQuantity||'';$('inspector').value=current.inspector||'';
    if(activeField)editor.value=current[activeField]||'';
    await change(current,true);
  }
});

async function retryPending() {
  for (const row of rows) {
    if (row.submittedAt || remote.conflicts.has(row.id)) continue;
    if (state(row).localError && !await persistDraft(row)) continue;
    if (row._pending || state(row).version > state(row).saved) void save(row);
  }
}
$('sync-summary').onclick = () => { void retryPending(); };

async function start() {
  syncViewport();renderLayout();
  try {
    const live = await remote.prepare();
    db = await openDatabase();
    const cached = await readRows();
    rows = live === null ? cached : remote.mergeCache(live,cached);
    for(const row of rows) {
      row._photoBase ||= row.photos.filter(p=>p.remoteId).map(p=>p.remoteId);
      state(row).localSaved = state(row).version;
    }
    await localWriteRows(rows);
    document.querySelector('.sandbox-note').textContent='手机保存，联网同步；提交审核请到电脑验货台';
    document.querySelector('.web-test').textContent='当前账号 · '+remote.context.actor.name;
    $('snapshot-notice').textContent = remote.offline ? '暂未连接系统，显示手机记录。可继续填写并保存，联网后自动同步。' : '';
    renderList({updateOptions:true});
    void retryPending();
    setInterval(()=>{void retryPending();void refreshLive();},15000);
    window.addEventListener('online',()=>{ $('snapshot-notice').textContent='网络已恢复，正在核对同步状态…';void retryPending();void refreshLive(); });
    window.addEventListener('offline',()=>{ $('snapshot-notice').textContent='已离线，填写仍可保存到手机；联网后自动同步。';renderList();if(current)refreshEntryStatus(current); });
    window.addEventListener('focus',()=>{void retryPending();void refreshLive();});
  } catch (error) {
    $('task-list').textContent='无法打开移动验货：'+error.message+'。已有手机记录不会被删除。';
    $('snapshot-notice').textContent='首次使用需从电脑扫码并联网；本机存储不可用时不能安全填写。';
  }
}
void start();
