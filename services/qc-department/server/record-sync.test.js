'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { DatabaseSync } = require('node:sqlite');
const source = fs.readFileSync(path.join(__dirname, 'server.js'), 'utf8');
const core = vm.runInNewContext(source.slice(source.indexOf('const RECORD_COLS'), source.indexOf('function replacePartners')) +
  ';({SCHEMA_SQL,upsertRecords,deleteRecords,mergeRecordChanges,replaceRecords,rowToRecord,nextRecordId,archiveSheetRecords})');
const catalog = vm.runInNewContext(source.slice(source.indexOf('const RECORD_COLS'), source.indexOf('/* 用户表新增字段')) +
  ';({replacePartners,replaceDefects,seedIfEmpty,getCatalogRevision})',
  { fs, SEED_PATH: path.join(__dirname, 'seed.json'), console: { log() {}, warn() {} } });
const record = (id, extra = {}) => ({ id, productNo: 'item-' + id, status: 'rejected', updatedAt: '2026-10-19T01:00:00Z', ...extra });
function database(t) { const db = new DatabaseSync(':memory:'); db.exec(core.SCHEMA_SQL); t.after(() => db.close()); return db; }
const all = db => db.prepare('SELECT * FROM records ORDER BY id').all().map(r => core.rowToRecord(r));

test('stale full arrays keep another browser record and its newer approval', t => {
  const db = database(t);
  core.upsertRecords(db, [record(1, { status: 'approved', updatedAt: '2026-10-19T03:00:00Z' }), record(2)]);
  const result = core.mergeRecordChanges(db, [record(1, { status: 'pending' }), record(3)], []);
  assert.equal(result.skippedStale, 1); assert.deepEqual(all(db).map(r => r.id), [1, 2, 3]);
  assert.equal(all(db)[0].status, 'approved');
});
test('missing timestamps and equal instants cannot roll back an existing record', t => {
  const db = database(t); core.upsertRecords(db, [record(1, { status: 'approved' })]);
  core.upsertRecords(db, [record(1, { status: 'pending', updatedAt: undefined })]);
  core.upsertRecords(db, [record(1, { status: 'pending', updatedAt: '2026-10-19T09:00:00+08:00' })]);
  assert.equal(all(db)[0].status, 'approved');
});
test('AQL multi-level values round-trip with all existing columns', t => {
  const db = database(t); core.upsertRecords(db, [record(1, { aqlLevel: 'MAJ 0.65,MIN 2.5', orderNo: 'PO-1', fail: 150, sampleQty: 100 })]);
  assert.equal(all(db)[0].aqlLevel, 'MAJ 0.65,MIN 2.5'); assert.equal(all(db)[0].orderNo, 'PO-1'); assert.equal(all(db)[0].fail, 150);
});
test('future-dated old tabs cannot resurrect a deleted record', t => {
  const db = database(t); core.upsertRecords(db, [record(1)]); core.deleteRecords(db, [1]);
  const result = core.upsertRecords(db, [record(1, { updatedAt: '2099-01-01T00:00:00Z' })]);
  assert.equal(result.skippedTomb, 1); assert.equal(all(db).length, 0);
});
test('mixed clear rolls back its audit and tombstones when a record is approved', t => {
  const db = database(t);
  core.upsertRecords(db, [record(1), record(2, {status:'approved'})]);
  assert.throws(() => core.replaceRecords(db, [], {actor:'fixture'}), /反审核/);
  assert.deepEqual(all(db).map(r => r.id), [1,2]);
  assert.equal(db.prepare('SELECT COUNT(*) n FROM qc_delete_history').get().n, 0);
  assert.equal(db.prepare('SELECT COUNT(*) n FROM record_tombstones').get().n, 0);
  core.deleteRecords(db, [1], true, {actor:'fixture'});
  const audit = db.prepare('SELECT actor,snapshot FROM qc_delete_history').get();
  assert.equal(audit.actor, 'fixture');
  assert.equal(JSON.parse(audit.snapshot).productNo, 'item-1');
});
test('clear and replacement preserve tombstones against an old full-array save', t => {
  const db = database(t); core.upsertRecords(db, [record(1), record(2)]); core.replaceRecords(db, []);
  core.upsertRecords(db, [record(1), record(2)]); assert.equal(all(db).length, 0);
  core.replaceRecords(db, [record(2, { productNo: 'explicit-import' })]);
  core.upsertRecords(db, [record(1, { updatedAt: '2099-01-01T00:00:00Z' })]);
  assert.deepEqual(all(db).map(r => r.id), [2]); assert.equal(all(db)[0].productNo, 'explicit-import');
});
test('sheet archive repeats safely after an identical record with the same id is restored', t => {
  const db = database(t);
  const original = record(42, { status: 'approved' });
  core.upsertRecords(db, [original]);
  const { version } = db.prepare('SELECT version FROM record_versions WHERE record_id=42').get();
  const { generation } = db.prepare('SELECT generation FROM record_generations WHERE record_id=42').get();
  const receipt = [{ id: 42, version, actor: 'qc-fixture' }];
  assert.deepEqual([...core.archiveSheetRecords(db, receipt)], ['archived']);
  assert.deepEqual(all(db), []);
  core.replaceRecords(db, [original]);
  assert.notEqual(db.prepare('SELECT generation FROM record_generations WHERE record_id=42').get().generation, generation);
  assert.deepEqual([...core.archiveSheetRecords(db, receipt)], ['archived']);
  assert.deepEqual(all(db).map(row => row.id), [42]);
  assert.equal(db.prepare('SELECT count(*) AS n FROM qc_delete_history').get().n, 1);
  assert.equal(db.prepare('SELECT count(*) AS n FROM record_tombstones').get().n, 0);
});
test('a newer version of a still-present legacy record is retained without an archive receipt', t => {
  const db = database(t);
  core.upsertRecords(db, [record(42)]);
  const { version } = db.prepare('SELECT version FROM record_versions WHERE record_id=42').get();
  const { generation } = db.prepare('SELECT generation FROM record_generations WHERE record_id=42').get();
  core.upsertRecords(db, [record(42, { updatedAt: '2026-10-20T01:00:00Z', remark: 'new' })]);
  assert.equal(db.prepare('SELECT generation FROM record_generations WHERE record_id=42').get().generation, generation);
  assert.deepEqual([...core.archiveSheetRecords(db, [{ id: 42, version, actor: 'qc-fixture' }])], ['retained']);
  assert.equal(all(db)[0].remark, 'new');
  assert.equal(db.prepare('SELECT count(*) AS n FROM record_archive_receipts').get().n, 0);
});
test('a missing legacy version never creates a verified receipt', t => {
  const db = database(t);
  core.upsertRecords(db, [record(42)]);
  const { version } = db.prepare('SELECT version FROM record_versions WHERE record_id=42').get();
  core.upsertRecords(db, [record(42, { updatedAt: '2026-10-20T01:00:00Z', remark: 'new' })]);
  core.deleteRecords(db, [42], true, { matchedSheetVersion: true });
  assert.deepEqual([...core.archiveSheetRecords(db, [{ id: 42, version, actor: 'qc-fixture' }])], ['absent']);
  assert.equal(db.prepare('SELECT count(*) AS n FROM record_archive_receipts').get().n, 0);
});
test('bootstrap high-water id stays above deleted ids so new records can be saved', t => {
  const db = database(t); core.upsertRecords(db, [record(500)]); core.deleteRecords(db, [500]);
  assert.equal(core.nextRecordId(db), 501);
  assert.equal(core.upsertRecords(db, [record(core.nextRecordId(db))]).accepted, 1);
  assert.deepEqual(all(db).map(r => r.id), [501]);
});
test('a bad upsert rolls back the same request deletion and its tombstone', t => {
  const db = database(t); core.upsertRecords(db, [record(1)]);
  assert.throws(() => core.mergeRecordChanges(db, [record(2, { supplier: { invalid: true } })], [1]));
  assert.deepEqual(all(db).map(r => r.id), [1]);
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM record_tombstones').get().n, 0);
});
test('failed explicit replacement restores both original rows and original tombstones', t => {
  const db = database(t); core.upsertRecords(db, [record(1), record(2)]); core.deleteRecords(db, [2]);
  assert.throws(() => core.replaceRecords(db, [record(3), record(3)]));
  assert.deepEqual(all(db).map(r => r.id), [1]);
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM record_tombstones WHERE id=2').get().n, 1);
});
test('old empty states remain locked for direct deletion and whole-library replacement', t => {
  const db = database(t);
  core.upsertRecords(db, [record(1, { status: null }), record(2, { status: '' })]);
  for (const id of [1, 2]) {
    assert.throws(() => core.deleteRecords(db, [id]), { qcStatus: 409 });
    assert.throws(() => core.replaceRecords(db, all(db).filter(row => row.id !== id)), { qcStatus: 409 });
  }
  assert.equal(all(db).length, 2);
  assert.equal(db.prepare('SELECT COUNT(*) n FROM qc_delete_history').get().n, 0);
});
test('replacement preserves unchanged locked rows and only archives actual removals', t => {
  const db = database(t);
  core.upsertRecords(db, [
    record(1, { status: 'approved', defects: [{ desc: '色差' }] }), record(2),
    record(3, { status: 'pending' }), record(4, { status: null }), record(5),
  ]);
  const [approved, removed, pending, legacy, editable] = all(db);
  const next = [approved, pending, legacy, { ...editable, productNo: 'edited' }, record(6)];
  const ctx = { actor: 'fixture', protectedIds: [1, 3, 4] };
  core.replaceRecords(db, next, ctx);
  assert.deepEqual(all(db).map(row => row.id), [1, 3, 4, 5, 6]);
  assert.deepEqual(all(db)[0], approved);
  assert.equal(all(db)[3].productNo, 'edited');
  const archive = db.prepare('SELECT item_key FROM qc_delete_history').all();
  assert.deepEqual(archive.map(row => row.item_key), [String(removed.id)]);
  assert.throws(() => core.replaceRecords(db, all(db).filter(row => row.id !== 6)
    .map(row => row.id === 1 ? { ...row, productNo: 'overwrite' } : row), ctx), { qcStatus: 409 });
  assert.deepEqual(all(db).map(row => row.id), [1, 3, 4, 5, 6]);
  assert.equal(db.prepare('SELECT COUNT(*) n FROM qc_delete_history').get().n, 1);
});
test('catalogs reject stale and unversioned resurrection and accept a fresh explicit add', t => {
  const db = database(t);
  const actor = 'fixture';
  const partners = ['supplier', 'customer', 'processType'].map(type => ({ type, name: '同名' }));
  assert.equal(catalog.replacePartners(db, partners, { actor, baseRevision: 0 }), 1);
  assert.equal(catalog.replacePartners(db, [], {
    actor, baseRevision: 1, removed: partners.map(p => [p.type, p.name]),
  }), 2);
  assert.throws(() => catalog.replacePartners(db, partners, { actor, baseRevision: 1 }), { qcStatus: 409 });
  assert.throws(() => catalog.replacePartners(db, partners, { actor, baseRevision: Number.MAX_SAFE_INTEGER + 1 }), { qcStatus: 422 });
  assert.throws(() => catalog.replacePartners(db, partners, { actor }), { qcStatus: 409 });
  assert.equal(db.prepare('SELECT COUNT(*) n FROM partners').get().n, 0);
  assert.equal(catalog.replacePartners(db, partners, { actor, baseRevision: 2 }), 3);
  assert.equal(db.prepare("SELECT COUNT(*) n FROM qc_delete_history WHERE kind='partners'").get().n, 3);

  catalog.seedIfEmpty(db, { includeRecords: false });
  const defaults = db.prepare('SELECT name, category, defaultLevel, enabled, createdAt FROM defect_library').all();
  assert.equal(defaults.length, 40);
  assert.equal(catalog.getCatalogRevision(db, 'defect_library'), 0);
  assert.equal(catalog.replaceDefects(db, [], { actor, baseRevision: 0, removed: defaults.map(d => [d.name]) }), 1);
  const color = defaults.find(d => d.name === '色差');
  assert.throws(() => catalog.replaceDefects(db, [color], { actor, baseRevision: 0 }), { qcStatus: 409 });
  assert.throws(() => catalog.replaceDefects(db, [color], { actor }), { qcStatus: 409 });
  catalog.seedIfEmpty(db, { includeRecords: false });
  assert.equal(db.prepare('SELECT COUNT(*) n FROM defect_library').get().n, 0);
  assert.equal(catalog.replaceDefects(db, [color], { actor, baseRevision: 1 }), 2);
  assert.equal(db.prepare('SELECT name FROM defect_library').get().name, '色差');
  assert.equal(db.prepare("SELECT COUNT(*) n FROM qc_delete_history WHERE kind='defect_library'").get().n, 40);
});
async function browser(catalogVersions) {
  const store = new Map([['nexus_qc_nexus:qc-test_hy-huaxing_records', JSON.stringify({ records: [] })]]);
  const requests = [];
  const sandbox = { window: { __QC_NEXUS: { company: 'hy-huaxing', user: { username: 'nexus:qc-test' } } }, location: { pathname: '/qc/' }, console: { log() {}, warn() {} },
    document: { addEventListener() {} }, sessionStorage: { getItem: key => store.get(key), setItem: (key, value) => store.set(key, value) },
    fetch: (url, options) => {
      if (options?.method === 'POST') {
        return new Promise(resolve => requests.push({ url, body: JSON.parse(options.body), resolve }));
      }
      assert.equal(url, '/qc/api/bootstrap?company=hy-huaxing');
      return Promise.resolve({ ok: true, status: 200, json: async () => ({ records: [], catalogVersions }) });
    }, setTimeout() {} };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../qc-backend.js'), 'utf8'), sandbox);
  await sandbox.window.__QC_BOOTSTRAP;
  assert.equal(sandbox.window.__QC_BACKEND_OK, true);
  return { window: sandbox.window, requests };
}
const tick = () => new Promise(resolve => setImmediate(resolve));
test('catalog saves use the loaded revisions and advance only the acknowledged catalog', async () => {
  const { window: w, requests } = await browser({ partners: 2, defectLib: 5 });
  const first = w.__QC_SAVE_PARTNERS([{ name: '甲', type: 'supplier' }]);
  assert.equal((await w.__QC_SAVE_PARTNERS([])).ok, false);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].body.baseRevision, 2);
  requests[0].resolve({ ok: false, status: 409, json: async () => ({ revision: 3, detail: '名单已更新' }) });
  assert.equal((await first).status, 409);
  assert.equal(w.__QC_CATALOG_VERSIONS.partners, 2);

  const next = w.__QC_SAVE_PARTNERS([{ name: '甲', type: 'supplier' }]);
  requests[1].resolve({ ok: true, status: 200, json: async () => ({ revision: 3 }) });
  assert.equal((await next).ok, true);
  assert.equal(w.__QC_CATALOG_VERSIONS.partners, 3);
  const defect = w.__QC_SAVE_DEFECTS([]);
  assert.equal(requests[2].body.baseRevision, 5);
  requests[2].resolve({ ok: true, status: 200, json: async () => ({ revision: 6 }) });
  await defect;
  assert.equal(w.__QC_CATALOG_VERSIONS.defectLib, 6);
  assert.equal(w.__QC_CATALOG_VERSIONS.partners, 3);
});
test('in-flight success only acknowledges the deletion revisions actually sent', async () => {
  const { window: w, requests } = await browser(); w.__QC_MARK_DELETED([1]); const first = w.__QC_SYNC_NOW(); await tick();
  w.__QC_MARK_DELETED([1, 2]); requests[0].resolve({ ok: true, status: 200 }); await first;
  assert.deepEqual(Array.from(w.__QC_PENDING_DELETES), [1, 2]);
  const second = w.__QC_SYNC_NOW(); await tick(); assert.deepEqual(requests[1].body.deletedIds, [1, 2]);
  requests[1].resolve({ ok: true, status: 200 }); await second; assert.equal(w.__QC_PENDING_DELETES.length, 0);
});
test('overlapping replacements remain serialized and the later generation is retained', async () => {
  const { window: w, requests } = await browser(); w.__QC_FORCE_REPLACE = 1; const first = w.__QC_SYNC_NOW(); await tick();
  w.__QC_FORCE_REPLACE = 2; const second = w.__QC_SYNC_NOW(); await tick(); assert.equal(requests.length, 1);
  requests[0].resolve({ ok: true, status: 200 }); await first; await tick(); assert.equal(requests.length, 2);
  assert.match(requests[1].url, /\/records\/replace\?/); assert.equal(w.__QC_FORCE_REPLACE, 2);
  requests[1].resolve({ ok: true, status: 200 }); await second; assert.equal(w.__QC_FORCE_REPLACE, false);
});
test('failed record writes retain pending deletes and a replacement for retry', async () => {
  const { window: w, requests } = await browser(); w.__QC_MARK_DELETED([3]); w.__QC_FORCE_REPLACE = 1;
  const pending = w.__QC_SYNC_NOW(); await tick(); requests[0].resolve({ ok: false, status: 500 }); await pending;
  assert.deepEqual(Array.from(w.__QC_PENDING_DELETES), [3]); assert.equal(w.__QC_FORCE_REPLACE, 1);
});

function appFunction(name, context) {
  const app = fs.readFileSync(path.join(__dirname, '../app.js'), 'utf8');
  const start = app.indexOf('function ' + name + '('), body = app.indexOf('{', start);
  assert.notEqual(start, -1);
  let depth = 0;
  for (let i = body; i < app.length; i++) {
    if (app[i] === '{') depth++;
    if (app[i] === '}' && --depth === 0) return vm.runInNewContext('(' + app.slice(start, i + 1) + ')', context);
  }
  throw new Error('Function boundary not found');
}
test('clear acknowledgement followed by new entry uses a fresh id above tombstones', t => {
  const db = database(t); core.upsertRecords(db, [record(500)]);
  const state = { records: [record(500)], nextId: 501 };
  const context = { state, window: {}, recs: () => state.records, _backupConfirm: options => options.onConfirm(),
    persist: () => core.replaceRecords(db, state.records), showToast() {}, _backupLog() {}, _backupRefreshAll() {} };
  appFunction('backupClearAll', context)();
  assert.equal(state.records.length, 0); assert.equal(state.nextId, 501);
  assert.equal(core.upsertRecords(db, [record(state.nextId++)]).accepted, 1);
});
test('backup replace uses the replacement channel and does not reset its allocated ids', () => {
  const state = { records: [record(500)], nextId: 501 };
  const context = { state, window: {}, nowIso: () => '2026-10-19T05:00:00Z', persist() {}, showToast() {}, _backupLog() {}, _backupRefreshAll() {} };
  for (const name of ['_pad', '_checkedDate', '_parseDate', '_dateDisplay']) context[name] = appFunction(name, context);
  appFunction('_backupDoImport', context)([{ productNo: 'imported' }], 'replace');
  assert.equal(state.records[0].date, ''); assert.equal(state.records[0].inspDate, '');
  assert.equal(state.records[0].id, 501); assert.equal(state.nextId, 502);
  assert.ok(context.window.__QC_FORCE_REPLACE);
});
