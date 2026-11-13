'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { JSDOM } = require('jsdom');
const app = fs.readFileSync(path.join(__dirname, 'app.js'), 'utf8');
const index = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
const reports = fs.readFileSync(path.join(__dirname, 'report_export.js'), 'utf8');
const bridge = fs.readFileSync(path.join(__dirname, 'nexus-integration.js'), 'utf8');
const backend = fs.readFileSync(path.join(__dirname, 'qc-backend.js'), 'utf8');

function functionSource(source, name) {
  const start = source.search(new RegExp('(?:async )?function ' + name + '\\('));
  assert.ok(start >= 0);
  const end = source.indexOf('\n}', start) + 2;
  return source.slice(start, end);
}

function workbenchBoot(context) {
  const dom = new JSDOM(index, {
    runScripts: 'outside-only',
    url: 'http://localhost/api/qc-department/huaxing/u-test/',
  });
  const w = dom.window;
  const d = w.document;
  const calls = [];
  const starts = [];
  const requests = [];
  const listen = d.addEventListener.bind(d);
  d.addEventListener = (event, callback, ...options) => {
    if (event === 'DOMContentLoaded') starts.push(callback);
    else listen(event, callback, ...options);
  };
  w.__QC_NEXUS = context;
  w.fetch = (url, options) => new Promise(resolve => requests.push({ url, options, resolve }));
  w.requestAnimationFrame = callback => callback();
  w.eval(backend);
  w.eval(app);
  w.showPage = page => calls.push(page);
  w.updateTopKpis = () => calls.push('kpis');
  return { dom, w, d, calls, requests, start: () => Promise.all(starts.map(start => start())) };
}

const qcContext = {
  factory: 'huaxing',
  company: 'hy-huaxing',
  exportAllowed: false,
  user: {
    username: 'nexus:qc-1',
    name: '<QC & reviewer>',
    role: 'viewer',
    perms: { dashboard: { v: 1 }, records: { v: 1, e: 1, a: 0, m: 0 } },
  },
};

test('QC loads through Nexus without exposing stale data or a second login while bootstrap is pending', async () => {
  const { dom, w, d, calls, requests, start } = workbenchBoot(qcContext);
  try {
    const wrapper = d.getElementById('appWrapper');
    const startup = d.getElementById('qcStartup');
    const recordsKey = 'nexus_qc_nexus:qc-1_hy-huaxing_records';
    const staleRecords = JSON.stringify({ records: [{ id: 1 }], nextId: 2 });
    w.sessionStorage.setItem(recordsKey, staleRecords);
    assert.ok(startup);
    assert.ok(startup.querySelector('.qc-orbit[aria-hidden="true"]'));
    assert.equal(startup.hidden, false);
    assert.equal(wrapper.style.display, 'none');
    assert.equal(d.querySelector('#loginScreen, input[type=password], [autocomplete=username]'), null);
    assert.equal(requests.length, 1, 'bootstrap GET starts before DOMContentLoaded');
    assert.match(requests[0].url, /\/api\/bootstrap\?company=hy-huaxing$/);
    assert.equal(requests[0].options?.method ?? 'GET', 'GET');
    const started = start();
    assert.equal(w.__QC_BACKEND_OK, false);
    assert.deepEqual(calls, []);
    assert.equal(wrapper.style.display, 'none');
    assert.equal(startup.hidden, false);
    assert.equal(w.recs().length, 0);
    assert.equal(w.sessionStorage.getItem(recordsKey), staleRecords);
    assert.equal(await w.__QC_SYNC_NOW(), false);
    assert.equal(requests.length, 1, 'writes remain unavailable until server data loads');

    const freshRecords = { records: [{ id: 31 }], nextId: 32 };
    requests[0].resolve({ ok: true, status: 200, json: async () => freshRecords });
    await started;
    assert.equal(w.__QC_BACKEND_OK, true);
    assert.deepEqual(JSON.parse(w.sessionStorage.getItem(recordsKey)), freshRecords);
    assert.deepEqual(Array.from(w.recs(), record => record.id), [31]);
    assert.ok(!startup.isConnected || startup.hidden || startup.style.display === 'none');
    assert.notEqual(wrapper.style.display, 'none');
    assert.equal(d.querySelector('input[type=password]'), null);
    assert.match(d.getElementById('userBadge').innerHTML, /&lt;QC &amp; reviewer&gt;/);
    assert.match(d.getElementById('userBadge').textContent, /Nexus 账号/);
    assert.deepEqual(calls, ['sales-schedule', 'kpis']);
    assert.equal(w.canView('records'), true);
    assert.equal(w.can('createRecord'), true);
    assert.equal(w.can('editRecord'), false);
    assert.equal(w.can('deleteRecord'), false);
    assert.equal(w.can('manageDefectLib'), false);
    assert.equal(w.can('exportPdf'), false);
  } finally {
    dom.window.close();
  }
});

for (const [label, context, message] of [
  ['without Nexus identity', undefined, /Nexus/],
  ['when QC data fails to load', qcContext, /QC 数据读取失败/],
]) {
  test('QC leaves business controls unavailable ' + label, async () => {
    const { dom, w, d, calls, requests, start } = workbenchBoot(context);
    try {
      const recordsKey = 'nexus_qc_nexus:qc-1_hy-huaxing_records';
      if (context) w.sessionStorage.setItem(recordsKey, JSON.stringify({ records: [{ id: 1 }] }));
      const started = start();
      if (context) {
        assert.equal(requests.length, 1);
        requests[0].resolve({ ok: false, status: 503 });
      } else {
        assert.equal(requests.length, 0);
      }
      await started;
      const wrapper = d.getElementById('appWrapper');
      assert.ok(!wrapper || wrapper.hidden || wrapper.style.display === 'none');
      assert.equal(d.querySelector('input[type=password]'), null);
      assert.match(d.body.textContent, message);
      assert.equal(d.querySelector('#qcStartup .qc-orbit'), null, 'failure replaces the loading animation');
      assert.notEqual(w.__QC_BACKEND_OK, true);
      assert.deepEqual(calls, []);
      if (context) {
        assert.equal(w.sessionStorage.getItem(recordsKey), null);
        assert.equal(await w.__QC_SYNC_NOW(), false);
        assert.equal(requests.length, 1);
      }
    } finally {
      dom.window.close();
    }
  });
}

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

for (const [source, name] of [[app, 'exportPDF'], [reports, 'exportReportPDF'], [reports, 'exportIQCReport']]) {
  test(name + ' refuses export before reading records or touching canvas', async () => {
    const messages = [];
    const context = { window: {}, can: () => false, showToast: value => messages.push(value) };
    await vm.runInNewContext(functionSource(source, name) + `;${name}();`, context);
    assert.deepEqual(messages, ['当前账号没有导出权限']);
  });
}

test('retired report-center PDF exports never read records or load canvas', async () => {
  for (const period of ['daily','weekly','monthly','yearly','analysis']) {
    const context = { can: () => true, document: {getElementById() {throw Error('retired PDF read');}} };
    await vm.runInNewContext(functionSource(reports,'exportReportPDF') + `;exportReportPDF('${period}');`,context);
  }
});

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


test('supplier PDF still exports through its independent canvas and restores its button', async () => {
  const saved=[],button={},canvas={offsetWidth:100,offsetHeight:50};
  const controls={supplierSelect:{value:'Test supplier'},supplierAppendix:{checked:true},btnExportSupplier:button};
  const context={can:()=>true,showToast:()=>{},document:{getElementById:id=>controls[id],body:{appendChild:()=>{},removeChild:()=>{}}},
    _rptShowOverlay:()=>{},_rptHideOverlay:()=>{},_rptUpdateOverlay:()=>{},_rptCheckDeps:async()=>true,
    _buildSupplierCanvas:(name,appendix)=>{assert.equal(name,'Test supplier');assert.equal(appendix,true);return canvas;},
    requestAnimationFrame:fn=>fn(),setTimeout:fn=>fn(),_todayStr:()=> '2026-11-13',
    html2canvas:async()=>({width:100,height:50,toDataURL:()=> 'data:image/jpeg;base64,test'}),
    window:{jspdf:{jsPDF:class{internal={getPageSize:()=>{},pageSize:{getWidth:()=>297,getHeight:()=>210}};addImage(){};save(name){saved.push(name);}}}},console};
  await vm.runInNewContext(functionSource(reports,'exportReportPDF')+";exportReportPDF('supplier');",context);
  assert.deepEqual(saved,['供应商质量报告_Test supplier_2026-11-13.pdf']);
  assert.equal(button.disabled,false);
});
