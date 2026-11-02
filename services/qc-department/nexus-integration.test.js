'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const app = fs.readFileSync(path.join(__dirname, 'app.js'), 'utf8');
const reports = fs.readFileSync(path.join(__dirname, 'report_export.js'), 'utf8');
const bridge = fs.readFileSync(path.join(__dirname, 'nexus-integration.js'), 'utf8');
const backend = fs.readFileSync(path.join(__dirname, 'qc-backend.js'), 'utf8');

function functionSource(source, name) {
  const start = source.search(new RegExp('(?:async )?function ' + name + '\\('));
  assert.ok(start >= 0);
  const end = source.indexOf('\n}', start) + 2;
  return source.slice(start, end);
}

test('Nexus login renders its escaped user badge and continues into dashboard', () => {
  const elements = new Map();
  const calls = [];
  const scope = { window: { __QC_NEXUS: {} },
    _liveUser: () => ({name: '<QC & reviewer>', username: 'qc', role: 'viewer'}),
    getCompanyObj: () => ({site: 'heyuan'}), getCompanyName: () => '河源华兴',
    getSiteObj: () => ({name: '河源'}), _initSidebar() {},
    document: {getElementById: id => {
      if (!elements.has(id)) elements.set(id, {style: {}, innerHTML: ''});
      return elements.get(id);
    }},
    applyPermissions: () => calls.push('permissions'),
    requestAnimationFrame: callback => callback(),
    showPage: page => calls.push(page), updateTopKpis: () => calls.push('kpis'),
    console: {error: (...args) => { throw new Error(args.join(' ')); }}
  };
  vm.runInNewContext(['_esc', '_renderUserBadge', '_showApp'].map(name => functionSource(app, name)).join('\n') + ';_showApp();', scope);
  assert.match(elements.get('userBadge').innerHTML, /&lt;QC &amp; reviewer&gt;/);
  assert.match(elements.get('userBadge').innerHTML, /Nexus 账号/);
  assert.deepEqual(calls, ['permissions', 'dashboard', 'kpis']);
});

test('an empty bootstrap preserves the authoritative id high-water mark', () => {
  const scope = { window: { __QC_NEXUS: {} }, sessionStorage: { getItem: () => JSON.stringify({ records: [], nextId: 501 }) }, LS_KEY: 'records', state: null };
  vm.runInNewContext(functionSource(app, 'initData') + ';initData();', scope);
  assert.equal(scope.state.nextId, 501);
  assert.equal(scope.state.records.length, 0);
});

test('sync failure freezes subsequent queued writes until a reload', async () => {
  const scope = { window: { __QC_NEXUS: {}, __QC_BACKEND_OK: true },
    document: { getElementById: () => ({}), addEventListener: () => {} },
    fetch: () => { throw new Error('a frozen bridge must not send a request'); } };
  vm.runInNewContext(bridge, scope);
  scope.window.__QC_SYNC_FAILURE();
  assert.equal(scope.window.__QC_BACKEND_OK, false);
  const saved = await vm.runInNewContext(functionSource(backend.replace(/^  /gm, ''), 'post') + ';post("/api/records", {});', scope);
  assert.equal(saved, false);
});

for (const [source, name] of [[app, 'exportPDF'], [app, 'exportMonthlyReportPDF'], [app, 'exportYearlyReportPDF'], [reports, 'exportReportPDF'], [reports, 'exportIQCReport']]) {
  test(name + ' refuses export before reading records or touching canvas', async () => {
    const messages = [];
    const context = { can: () => false, showToast: value => messages.push(value) };
    await vm.runInNewContext(functionSource(source, name) + `;${name}();`, context);
    assert.deepEqual(messages, ['当前账号没有导出权限']);
  });
}

test('JSON export rejects missing export permission before reading any records', () => {
  const messages = [];
  vm.runInNewContext(functionSource(app, 'backupExportJSON') + ';backupExportJSON();', {
    can: () => false, showToast: message => messages.push(message),
    recs: () => { throw new Error('must not read data'); }
  });
  assert.equal(messages.length, 1);
});
test('recorders keep free text without writing unauthorized defect master data', () => {
  assert.equal(vm.runInNewContext(functionSource(app, '_checkUnknownDefects') + ';_checkUnknownDefects([{desc:"new"}]);', {
    can: () => false, _getDefectLib: () => { throw new Error('must not use master data'); }
  }), true);
});
test('empty or embedded seed restoration cannot replace records', () => {
  for (const embedded of [false, true]) {
    const context = { window: { __QC_NEXUS: embedded }, SEED_RECORDS: embedded ? [{id:1}] : [], showToast() {},
      _backupConfirm() { throw new Error('must not reach destructive confirmation'); } };
    vm.runInNewContext(functionSource(app, 'backupRestoreSeed') + ';backupRestoreSeed();', context);
    assert.equal(context.window.__QC_FORCE_REPLACE, undefined);
  }
});
test('reports use escaped current company and visibly label reference data', () => {
  const context = { window: {}, getCompanyName: () => '华兴<&' };
  vm.runInNewContext(functionSource(app, '_esc') + '\n' + functionSource(app, 'getReportCompanyLabel'), context);
  assert.equal(context.getReportCompanyLabel(), '华兴&lt;&amp;');
  context.window.__QC_REFERENCE_DATA = { count: 30 };
  assert.match(context.getReportCompanyLabel(), /模板参考（非本厂实绩）/);
});

test('reference JSON backup cannot silently become real data on re-import', () => {
  const result = vm.runInNewContext(functionSource(app, '_backupValidate') + ';_backupValidate({referenceData:{count:30},records:[{date:"2026-10-20",supplier:"test"}]});');
  assert.match(result, /包含模板参考/);
});
test('reference clear waits for queued saves and blocks duplicate interaction', async () => {
  let resolveSave, requests = 0, overlays = 0, reloads = 0;
  const scope = { can: () => true, confirm: () => true, alert() {},
    window: { __QC_REFERENCE_DATA: {count:30}, __QC_SYNC_NOW: () => new Promise(resolve => { resolveSave = resolve; }), location:{reload:()=>reloads++} },
    document: { addEventListener() {}, createElement: () => ({setAttribute(){},style:{}}), body:{appendChild:()=>overlays++} },
    fetch: async () => { requests++; return {ok:true,json:async()=>({deleted:30,protectedCount:0})}; }
  };
  vm.runInNewContext(bridge, scope);
  const clearing = scope.window.clearQcReferenceData();
  assert.equal(requests,0); assert.equal(overlays,1);
  await scope.window.clearQcReferenceData(); assert.equal(overlays,1);
  resolveSave(true); await clearing;
  assert.equal(requests,1); assert.equal(reloads,1);
});
test('failed queued save prevents reference deletion', async () => {
  let failed = 0;
  const scope = { can: () => true, confirm: () => true, alert() {},
    window: { __QC_REFERENCE_DATA: {count:30}, __QC_SYNC_NOW: async()=>false },
    document: { addEventListener() {}, createElement: () => ({setAttribute(){},style:{}}), body:{appendChild(){}} },
    fetch: () => { throw new Error('must not delete'); }
  };
  vm.runInNewContext(bridge, scope); scope.window.__QC_SYNC_FAILURE = () => failed++;
  await scope.window.clearQcReferenceData(); assert.equal(failed,1);
});


test('new imported rows retain account name across repeated sync without touching historical inspectors', () => {
  const scope={window:{__QC_NEXUS:{inspector:{id:'qc-1',name:'当前检验员'}},__QC_KNOWN_RECORD_IDS:new Set([31])},state:{records:[{id:31,qc:'历史检验员'},{id:78,qc:'导入姓名'}]}};
  const source=functionSource(app,'_bindNewQcInspectors');
  vm.runInNewContext(source+';_bindNewQcInspectors();',scope);
  assert.equal(scope.state.records[0].qc,'历史检验员');
  assert.equal(scope.state.records[1].qc,'当前检验员');
  const first=JSON.stringify(scope.state.records);
  vm.runInNewContext('_bindNewQcInspectors();',scope);
  assert.equal(JSON.stringify(scope.state.records),first);
});
