'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const project = process.env.QC_TEST_PROJECT || path.resolve(__dirname, '../..');
const { JSDOM } = require(path.join(project, 'node_modules/jsdom'));
const sourceRoot = process.env.QC_TEST_SOURCE || project;

const html = fs.readFileSync(path.join(sourceRoot, 'services/qc-department/index.html'), 'utf8');
const columns = [
  'date', 'customer', 'poNo', 'country', 'productNo', 'productName', 'quantity',
  'unitsPerCarton', 'cartonCount', 'production', 'agency', 'customerPo',
  'completion', 'result', 'remark', 'photos', 'improvement', 'submit',
].map((key, idx) => ({
  key,
  label: [
    '日期', '客户', 'PO#', '出口国', '货号', '产品名称', '数量', '装箱', '箱数',
    '生产', '机构', '客PO#', '完成情况', '验货结果', '备注', '照片', '改进措施', '提交',
  ][idx],
}));

const tick = (ms = 10) => new Promise((resolve) => setTimeout(resolve, ms));
const copy = (v) => JSON.parse(JSON.stringify(v));

async function createSheetEnv({ deleteAllowed }) {
  const dom = new JSDOM(html, {
    runScripts: 'outside-only',
    url: 'http://localhost/api/qc-department/huaxing/u-test/',
  });
  const w = dom.window;
  const d = w.document;
  const calls = [];
  let entries = [
    {
      id: 'wb-blank', sourceKey: 'desk:manual:1', customer: 'ZURU', poNo: 'PO-BLANK',
      productNo: 'SKU-BLANK', productName: '空白草稿', result: '', remark: '',
      photos: [], revision: 1, dateFrom: '2026-11-26', dateTo: '2026-11-26', updatedAt: '',
    },
    {
      id: 'wb-filled', sourceKey: 'workflow:t1', customer: 'MGA', poNo: 'PO-FILLED',
      productNo: 'SKU-FILLED', productName: '已填产品', result: 'PASS', remark: 'ok',
      photos: [], revision: 2, dateFrom: '2026-11-26', dateTo: '2026-11-26', updatedAt: '',
    },
  ];
  let reviewEntries = [
    {
      id: 'rev-pending-1', sourceKey: 'desk:manual:2', customer: 'ZURU', poNo: 'PO-PEND-1',
      productNo: 'SKU-PEND-1', productName: '待审产品', result: 'PASS', remark: '待审',
      photos: [], revision: 3, reviewState: 'pending', submittedAt: '2026-11-25T02:00:00Z',
      dateFrom: '2026-11-26', dateTo: '2026-11-26', updatedAt: '',
    },
    {
      id: 'rev-approved-1', sourceKey: 'desk:manual:3', customer: 'ZURU', poNo: 'PO-APPR-1',
      productNo: 'SKU-APPR-1', productName: '已审产品', result: 'PASS', remark: '已审',
      photos: [], revision: 4, reviewState: 'approved', submittedAt: '2026-11-25T01:00:00Z',
      confirmedAt: '2026-11-25T01:30:00Z', confirmedBy: '主管',
      dateFrom: '2026-11-26', dateTo: '2026-11-26', updatedAt: '',
    },
  ];
  w.requestAnimationFrame = (fn) => w.setTimeout(fn, 1);
  w.cancelAnimationFrame = (id) => w.clearTimeout(id);
  w.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  w.HTMLDialogElement.prototype.close = function () { this.open = false; this.dispatchEvent(new w.Event('close')); };
  w.__QC_NEXUS = {
    exportAllowed: true,
    deleteAllowed,
    workflow: { edit: true, review: true, manual: true, delete: deleteAllowed },
  };
  w.QcReportWorkbook = {
    openReview: () => {},
    trigger: (label, fn) => {
      const btn = d.createElement('button');
      btn.type = 'button';
      btn.textContent = label;
      btn.onclick = fn;
      return btn;
    },
  };
  w.showToast = (msg, type) => calls.push({ toast: msg, type });
  w.fetch = async (url, options = {}) => {
    const body = options.body ? JSON.parse(options.body) : null;
    calls.push({ url, body });
    if (url.endsWith('/options')) return { ok: true, json: async () => ({ inspectors: [], institutions: [] }) };
    if (url.endsWith('/review/entries')) return { ok: true, json: async () => ({ items: copy(reviewEntries), columns }) };
    if (url.endsWith('/entries')) return { ok: true, json: async () => ({ items: copy(entries), columns }) };
    if (url.endsWith('/notifications')) return { ok: true, json: async () => ({ items: [] }) };
    if (url.endsWith('/entries/delete')) {
      const ids = new Set(body.entries.map((e) => e.id));
      entries = entries.filter((e) => !ids.has(e.id));
      return { ok: true, json: async () => ({ results: body.entries.map((e) => ({ id: e.id, ok: true })), succeeded: ids.size, failed: 0 }) };
    }
    if (url.endsWith('/review/delete')) {
      const ids = new Set(body.entries.map((e) => e.id));
      reviewEntries = reviewEntries.filter((e) => !ids.has(e.id));
      return { ok: true, json: async () => ({ results: body.entries.map((e) => ({ id: e.id, ok: true })), succeeded: ids.size, failed: 0 }) };
    }
    return { ok: true, json: async () => ({}) };
  };
  w.eval(fs.readFileSync(path.join(sourceRoot, 'services/qc-department/qc-schedule.js'), 'utf8'));
  w.eval(fs.readFileSync(path.join(sourceRoot, 'services/qc-department/qc-inspection-audit.js'), 'utf8'));
  w.eval(fs.readFileSync(path.join(sourceRoot, 'services/qc-department/qc-photo-paste.js'), 'utf8'));
  w.eval(fs.readFileSync(path.join(sourceRoot, 'services/qc-department/qc-review-workbook.js'), 'utf8'));
  w.eval(fs.readFileSync(path.join(sourceRoot, 'services/qc-department/qc-inspection-sheet.js'), 'utf8'));
  await tick();
  if (!w.QcInspectionSheet.model.loaded) await w.QcInspectionSheet.load('records');
  return { dom, w, d, calls };
}

test('ordinary user sees zero delete UI in workbench and review center', async () => {
  const env = await createSheetEnv({ deleteAllowed: false });
  try {
    assert.equal(env.d.querySelector('th[data-column="deleteSelect"]'), null);
    assert.equal(env.d.getElementById('qis-record-delete'), null);
    assert.equal(env.d.querySelectorAll('#recordsTableWrap thead th').length, 18);

    await env.w.QcInspectionSheet.loadReview('pending');
    assert.equal(env.d.querySelector('#reviewTableWrap th[data-column="deleteSelect"]'), null);
    assert.equal(env.d.getElementById('qis-review-delete'), null);
    assert.equal(env.d.querySelector('.qis-approved-delete-guide'), null);

    await env.w.QcInspectionSheet.loadReview('approved');
    assert.equal(env.d.getElementById('qis-review-delete'), null);
    assert.equal(env.d.querySelector('.qis-approved-delete-guide'), null);
  } finally {
    env.dom.window.close();
  }
});

test('QC_test can delete blank drafts in workbench, pending items in review, and sees revoke-first guard on approved tab', async () => {
  const env = await createSheetEnv({ deleteAllowed: true });
  try {
    // Workbench shows frozen delete checkbox column + bottom-left delete button.
    assert.ok(env.d.querySelector('#recordsTableWrap th[data-column="deleteSelect"]'));
    const delBtn = env.d.getElementById('qis-record-delete');
    const submitBtn = env.d.getElementById('qis-record-batch');
    assert.ok(delBtn && delBtn.disabled);

    // Check a BLANK draft row -> enables delete button while submit stays disabled!
    const blankCheck = env.d.querySelector('[data-delete-check="wb-blank"]');
    blankCheck.checked = true;
    blankCheck.dispatchEvent(new env.w.Event('change'));
    assert.equal(delBtn.disabled, false);
    assert.equal(delBtn.textContent, '删除所选记录（1）');
    assert.equal(submitBtn.disabled, true);

    // Open confirm modal, enter reason, confirm deletion.
    delBtn.click();
    const dlg = env.d.querySelector('dialog[open]');
    assert.ok(dlg);
    assert.match(dlg.textContent, /PO-BLANK/);
    assert.match(dlg.textContent, /不会影响业务部「客排期」/);
    dlg.querySelector('[data-delete-reason]').value = '清理空白草稿';
    dlg.querySelector('[data-execute]').click();
    await tick(20);

    const wbCall = env.calls.find((c) => c.url?.endsWith('/entries/delete'));
    assert.ok(wbCall);
    assert.deepEqual(wbCall.body.entries, [{ id: 'wb-blank', revision: 1 }]);
    assert.equal(wbCall.body.reason, '清理空白草稿');
    assert.equal(env.d.querySelector('[data-entry="wb-blank"]'), null);
    assert.ok(env.d.querySelector('[data-entry="wb-filled"]'));

    // Review center -> pending tab shows delete column & toolbar button.
    await env.w.QcInspectionSheet.loadReview('pending');
    const revDelBtn = env.d.getElementById('qis-review-delete');
    assert.ok(revDelBtn && !revDelBtn.hidden && revDelBtn.disabled);
    const guide = env.d.querySelector('.qis-approved-delete-guide');
    assert.ok(guide && guide.hidden);

    const pendCheck = env.d.querySelector('[data-delete-check="rev-pending-1"]');
    pendCheck.checked = true;
    pendCheck.dispatchEvent(new env.w.Event('change'));
    assert.equal(revDelBtn.disabled, false);
    assert.equal(revDelBtn.textContent, '删除所选（1）');
    revDelBtn.click();
    const revDlg = env.d.querySelector('dialog[open]');
    assert.ok(revDlg && /PO-PEND-1/.test(revDlg.textContent));
    revDlg.querySelector('[data-execute]').click();
    await tick(20);
    assert.ok(env.calls.some((c) => c.url?.endsWith('/review/delete')));
    assert.equal(env.d.getElementById('reviewCountPending').textContent, '0');

    // Review center -> approved tab hides delete button and shows amber revoke-first guidance.
    await env.w.QcInspectionSheet.loadReview('approved');
    assert.equal(env.d.getElementById('qis-review-delete').hidden, true);
    assert.equal(env.d.querySelector('.qis-approved-delete-guide').hidden, false);
    assert.match(env.d.querySelector('.qis-approved-delete-guide').textContent, /反审核/);
  } finally {
    env.dom.window.close();
  }
});

async function createSummaryEnv({ deleteAllowed }) {
  const dom = new JSDOM(html, {
    runScripts: 'outside-only',
    url: 'http://localhost/api/qc-department/huaxing/u-test/',
  });
  const w = dom.window;
  const d = w.document;
  const calls = [];
  const summaryRecords = [
    {
      id: '1'.repeat(32), customer: 'ZURU', poNo: 'PO-HIST-1', productNo: 'SKU-H1',
      inspectionDate: '2025-03-15', reportDate: '2025-03-15', stockNo: '', inspectionType: '待确认',
      result: 'PASS', status: 'unverified', sourceKind: 'history', sourceFilename: '历史表.xlsx',
      historyBatchId: '2'.repeat(32),
    },
    {
      id: '3'.repeat(32), entryId: 'e-rev-1', customer: 'MGA', poNo: 'PO-REV-1', productNo: 'SKU-R1',
      inspectionDate: '2026-11-25', reportDate: '2026-11-25', stockNo: '', inspectionType: '行验',
      result: 'PASS', status: 'approved', sourceKind: 'review',
    },
  ];
  w.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  w.HTMLDialogElement.prototype.close = function () { this.open = false; this.dispatchEvent(new w.Event('close')); };
  w.__QC_NEXUS = { summaryImportAllowed: true, deleteAllowed, workflow: { delete: deleteAllowed } };
  w.showToast = (msg, type) => calls.push({ toast: msg, type });
  w.showPage = (page) => calls.push({ page });
  w.QcInspectionSheet = { loadReview: (tab) => calls.push({ loadReview: tab }) };
  w.fetch = async (url, options = {}) => {
    const body = options.body ? JSON.parse(options.body) : null;
    calls.push({ url, body });
    if (url.startsWith('api/inspection-summary/records?')) {
      return { ok: true, json: async () => ({ items: copy(summaryRecords), total: summaryRecords.length, page: 1, pageSize: 30, years: ['2025', '2026'], counts: { 已审核: 1, 历史待核实: 1 }, unknownDates: 0 }) };
    }
    if (url.startsWith('api/inspection-dossier/records/')) {
      const id = url.split('/').at(-1);
      const qc = summaryRecords.find((r) => r.id === id);
      return { ok: true, json: async () => ({ qc: copy(qc), business: { status: 'missing' }, audit: [], changes: [], sourceEvents: [] }) };
    }
    if (url === 'api/inspection-summary/history/batches') {
      return { ok: true, json: async () => ({ items: [{ id: '2'.repeat(32), filename: '历史表.xlsx', status: 'committed', committedAt: '2026-11-25T01:00:00Z', totalRows: 5, activeCount: 5 }] }) };
    }
    if (url.endsWith('/delete')) return { ok: true, json: async () => ({ id: '1'.repeat(32), status: 'deleted' }) };
    if (url.endsWith('/rollback')) return { ok: true, json: async () => ({ id: '2'.repeat(32), status: 'rolled_back', rolledBackCount: 5 }) };
    return { ok: true, json: async () => ({}) };
  };
  w.eval(fs.readFileSync(path.join(sourceRoot, 'services/qc-department/qc-inspection-audit.js'), 'utf8'));
  w.eval(fs.readFileSync(path.join(sourceRoot, 'services/qc-department/qc-inspection-summary.js'), 'utf8'));
  await w.QcInspectionSummary.load();
  return { dom, w, d, calls };
}

test('inspection summary hides admin controls for ordinary user and provides history delete, batch rollback, and review guard for QC_test', async () => {
  const ordinary = await createSummaryEnv({ deleteAllowed: false });
  try {
    assert.equal(ordinary.d.getElementById('qsum-manage-batches'), null);
    ordinary.d.querySelector('[data-summary-id="' + '1'.repeat(32) + '"]').click();
    await tick(20);
    assert.equal(ordinary.d.querySelector('.qsum-admin-zone'), null);
  } finally {
    ordinary.dom.window.close();
  }

  const admin = await createSummaryEnv({ deleteAllowed: true });
  try {
    const batchBtn = admin.d.getElementById('qsum-manage-batches');
    assert.ok(batchBtn);
    batchBtn.click();
    await tick(20);
    const batchDlg = admin.d.querySelector('dialog[open]');
    assert.ok(batchDlg && /历史表\.xlsx/.test(batchDlg.textContent));
    batchDlg.querySelector('[data-batch-rollback]').click();
    await tick(10);
    const confirmRb = [...admin.d.querySelectorAll('dialog[open]')].at(-1);
    confirmRb.querySelector('[data-execute]').click();
    await tick(20);
    assert.ok(admin.calls.some((c) => c.url === 'api/inspection-summary/history/' + '2'.repeat(32) + '/rollback'));
    batchDlg.close();

    // History record detail offers delete button.
    admin.d.querySelector('[data-summary-id="' + '1'.repeat(32) + '"]').click();
    await tick(20);
    const histDlg = admin.d.querySelector('dialog[open]');
    assert.ok(histDlg.querySelector('[data-delete-history-record]'));
    assert.ok(histDlg.querySelector('[data-rollback-same-batch]'));
    histDlg.querySelector('[data-delete-history-record]').click();
    await tick(10);
    const confirmDel = [...admin.d.querySelectorAll('dialog[open]')].at(-1);
    confirmDel.querySelector('[data-execute]').click();
    await tick(20);
    assert.ok(admin.calls.some((c) => c.url === 'api/inspection-summary/records/' + '1'.repeat(32) + '/delete'));

    // Review-synced record detail offers NO delete button, only guidance to review center approved tab.
    admin.d.querySelector('[data-summary-id="' + '3'.repeat(32) + '"]').click();
    await tick(20);
    const revDlg = admin.d.querySelector('dialog[open]');
    assert.equal(revDlg.querySelector('[data-delete-history-record]'), null);
    const gotoBtn = revDlg.querySelector('[data-goto-review-approved]');
    assert.ok(gotoBtn);
    gotoBtn.click();
    assert.ok(admin.calls.some((c) => c.page === 'review'));
    assert.ok(admin.calls.some((c) => c.loadReview === 'approved'));
  } finally {
    admin.dom.window.close();
  }
});

test('app.js isolates user badge pill, defect delete, partner delete, and destructive import cards behind record_delete', async () => {
  const appScript = fs.readFileSync(path.join(sourceRoot, 'services/qc-department/app.js'), 'utf8');

  async function mountApp({ deleteAllowed }) {
    const dom = new JSDOM(html, {
      runScripts: 'outside-only',
      url: 'http://localhost/api/qc-department/huaxing/u-test/',
    });
    const w = dom.window;
    const d = w.document;
    const toasts = [];
    w.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
    w.requestAnimationFrame = () => 0;
    w.cancelAnimationFrame = () => {};
    w.confirm = () => true;
    w.__QC_NEXUS = {
      factory: 'huaxing',
      company: 'hy-huaxing',
      exportAllowed: true,
      deleteAllowed,
      workflow: { create: true, edit: true, review: true, export: true, manual: true, delete: deleteAllowed },
      user: {
        username: deleteAllowed ? 'nexus:user-qc-test' : 'nexus:user-supervisor',
        name: deleteAllowed ? 'QC 数据管理员' : '普通主管',
        role: 'viewer',
        enabled: true,
        perms: {
          dashboard: { v: 1, e: 0, a: 0, m: 0 },
          'sales-schedule': { v: 1, e: 0, a: 0, m: 0 },
          records: { v: 1, e: 1, a: 1, m: deleteAllowed ? 1 : 0 },
          review: { v: 1, e: 1, a: 1, m: deleteAllowed ? 1 : 0 },
          'inspection-summary': { v: 1, e: 0, a: 0, m: 0 },
          analysis: { v: 1, e: 0, a: 0, m: 0 },
          suppliers: { v: 1, e: 1, a: 1, m: 1 },
          daily: { v: 1, e: 0, a: 0, m: 0 },
          weekly: { v: 1, e: 0, a: 0, m: 0 },
          monthly: { v: 1, e: 0, a: 0, m: 0 },
          yearly: { v: 1, e: 0, a: 0, m: 0 },
          'supplier-report': { v: 1, e: 0, a: 0, m: 0 },
          defectlib: { v: 1, e: 1, a: 1, m: 1 },
          import: { v: 1, e: 0, a: 0, m: deleteAllowed ? 1 : 0 },
        },
      },
    };
    w.eval(appScript);
    w.showToast = (msg, type) => toasts.push({ msg, type });
    w.eval(`
      _saveDefectLib([
        { name: '缩水', category: '外观/质量', defaultLevel: 'MAJ 1.0', keywords: [], enabled: true },
        { name: '未用词条', category: '外观/质量', defaultLevel: 'MIN 2.5', keywords: [], enabled: true },
      ]);
      _savePartners([{ type: 'supplier', name: '天一' }]);
      _renderUserBadge(); applyPermissions(); renderDefectLibPage(); renderPartners('supplier');
    `);
    return { dom, w, d, toasts };
  }

  // Ordinary supervisor: NO pill, NO delete buttons in defectlib/partners, destructive import cards hidden,
  // while add/edit/disable stay available!
  const sup = await mountApp({ deleteAllowed: false });
  try {
    assert.equal(sup.d.querySelector('.qc-delete-role-pill'), null);
    assert.equal(sup.d.querySelector('#page-import .backup-card.red').style.display, 'none');
    assert.equal(sup.d.querySelector('#page-import .backup-card.yellow').style.display, 'none');
    assert.ok(sup.d.querySelector('#page-defectlib').textContent.includes('新增描述'));
    assert.ok(sup.d.querySelector('#page-defectlib').textContent.includes('停用'));
    assert.equal(sup.d.querySelector('#page-defectlib .action-btn.del'), null);
    assert.ok(sup.d.querySelector('#partnerMgr_supplier button[onclick^="addPartner"]'));
    assert.equal(sup.d.querySelector('#partnerMgr_supplier button[onclick^="delPartner"]'), null);
  } finally {
    sup.dom.window.close();
  }

  // QC_test: sees pill, destructive cards, defectlib "删除描述" (with 409 rollback protection), and partner delete "✕".
  const adm = await mountApp({ deleteAllowed: true });
  try {
    assert.ok(adm.d.querySelector('.qc-delete-role-pill'));
    assert.equal(adm.d.querySelector('#page-import .backup-card.red').style.display, '');
    assert.equal(adm.d.querySelector('#page-import .backup-card.yellow').style.display, '');
    const delBtns = adm.d.querySelectorAll('#page-defectlib .action-btn.del');
    assert.equal(delBtns.length, 2);
    assert.equal(delBtns[0].textContent, '删除描述');
    assert.ok(adm.d.querySelector('#partnerMgr_supplier button[onclick^="delPartner"]'));

    // Simulate backend 409 when trying to delete referenced defect "缩水" -> stays intact and shows toast!
    adm.w.__QC_BACKEND_OK = true;
    adm.w.__QC_SAVE_DEFECTS = async () => ({ ok: false, status: 409, detail: '不良描述「缩水」已被历史验货记录引用，请改用「停用」' });
    await adm.w._deleteDefLibItem(0);
    const storedAfter409 = adm.w.eval('_getDefectLib()');
    assert.equal(storedAfter409.length, 2);
    assert.ok(adm.toasts.some((t) => t.type === 'error' && t.msg.includes('停用')));

    // Simulate backend 200 when deleting unreferenced defect "未用词条" -> removed!
    adm.w.__QC_SAVE_DEFECTS = async () => ({ ok: true, status: 200, detail: '' });
    await adm.w._deleteDefLibItem(1);
    const storedAfter200 = adm.w.eval('_getDefectLib()');
    assert.deepEqual(Array.from(storedAfter200, (x) => x.name), ['缩水']);
  } finally {
    adm.dom.window.close();
  }
});
