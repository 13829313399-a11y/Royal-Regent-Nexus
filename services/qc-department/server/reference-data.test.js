'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { DatabaseSync } = require('node:sqlite');
const { referenceData, clearReferenceData, importReferenceData } = require('./reference-data');
const source = fs.readFileSync(__dirname + '/server.js', 'utf8');
const core = vm.runInNewContext(source.slice(source.indexOf('const RECORD_COLS'), source.indexOf('function replaceUsers')) +
  ';({SCHEMA_SQL,upsertRecords,deleteRecords})');
function database(t) { const db = new DatabaseSync(':memory:'); db.exec(core.SCHEMA_SQL); t.after(() => db.close()); return db; }
function row(id, productNo = 'reference') { return { id, productNo, updatedAt: '2026-10-20T00:00:00Z' }; }
test('reference import preserves source, avoids live/tombstoned IDs and is idempotent', t => {
  const src = database(t), target = database(t);
  core.upsertRecords(src, [row(1), row(2)]);
  core.upsertRecords(target, [row(1, 'live')]); core.deleteRecords(target, [2]);
  const original = JSON.stringify(src.prepare('SELECT * FROM records').all());
  assert.equal(importReferenceData(src, target, 'dg-xingxin', 'batch').imported, 2);
  assert.equal(importReferenceData(src, target, 'dg-xingxin', 'batch').imported, 0);
  assert.equal(target.prepare('SELECT productNo FROM records WHERE id=1').get().productNo, 'live');
  assert.equal(target.prepare('SELECT COUNT(*) c FROM records').get().c, 3);
  assert.equal(JSON.stringify(src.prepare('SELECT * FROM records').all()), original);
  assert.ok(referenceData(target).ids.every(id => id !== 1 && id !== 2));
});
test('clear removes only unchanged references and tombstones block stale resurrection', t => {
  const src = database(t), target = database(t);
  core.upsertRecords(src, [row(1), row(2)]); importReferenceData(src, target, 'dg-xingxin', 'batch');
  core.upsertRecords(target, [row(3, 'new real record')]);
  target.prepare('UPDATE records SET productNo=? WHERE id=2').run('edited reference');
  const result = clearReferenceData(target, core.deleteRecords);
  assert.equal(result.deleted, 1); assert.equal(result.protectedCount, 1);
  assert.deepEqual(target.prepare('SELECT id FROM records ORDER BY id').all().map(r => r.id), [2, 3]);
  assert.equal(referenceData(target).modifiedCount, 1);
  core.upsertRecords(target, [row(1)]);
  assert.equal(target.prepare('SELECT id FROM records WHERE id=1').get(), undefined);
  assert.equal(clearReferenceData(target, core.deleteRecords).deleted, 0);
});
test('clear rolls back record deletions and provenance on failure', t => {
  const src = database(t), target = database(t);
  core.upsertRecords(src, [row(1)]); importReferenceData(src, target, 'dg-xingxin', 'batch');
  assert.throws(() => clearReferenceData(target, (db, ids) => {
    core.deleteRecords(db, ids, false); throw new Error('forced failure');
  }), /forced failure/);
  assert.equal(referenceData(target).count, 1);
  assert.equal(target.prepare('SELECT COUNT(*) c FROM record_tombstones').get().c, 0);
});
test('a company without references is untouched and schemas must match', t => {
  const src = database(t), target = database(t);
  core.upsertRecords(target, [row(8, 'live')]);
  assert.equal(clearReferenceData(target, core.deleteRecords).deleted, 0);
  src.exec('ALTER TABLE records ADD COLUMN newer TEXT');
  assert.throws(() => importReferenceData(src, target, 'dg-xingxin', 'batch'), /schemas differ/);
  assert.equal(target.prepare('SELECT COUNT(*) c FROM records').get().c, 1);
});
