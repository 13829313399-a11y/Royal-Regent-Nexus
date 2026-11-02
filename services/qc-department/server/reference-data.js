'use strict';

// Provenance is separate from inspection fields; importing never overwrites a row.
const TABLE = 'qc_reference_records';
function references(db) {
  if (!db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name=?").get(TABLE)) return [];
  return db.prepare(`SELECT * FROM ${TABLE}`).all();
}
function unchanged(row, reference) {
  const baseline = JSON.parse(reference.baseline_json);
  return row && Object.entries(baseline).every(([key, value]) => row[key] === value);
}
function referenceData(db) {
  const get = db.prepare('SELECT * FROM records WHERE id=?');
  const rows = references(db).filter(ref => get.get(ref.record_id));
  return { count: rows.length, ids: rows.map(r => r.record_id),
    modifiedCount: rows.filter(r => !unchanged(get.get(r.record_id), r)).length,
    sourceCompanies: [...new Set(rows.map(r => r.source_company))] };
}
function clearReferenceData(db, deleteRecords) {
  db.exec('BEGIN IMMEDIATE');
  try {
    const refs = references(db);
    const get = db.prepare('SELECT * FROM records WHERE id=?');
    const eligible = refs.filter(r => unchanged(get.get(r.record_id), r));
    const deleted = deleteRecords(db, eligible.map(r => r.record_id), false);
    if (refs.length) db.exec(`DELETE FROM ${TABLE} WHERE record_id NOT IN (SELECT id FROM records)`);
    const remaining = referenceData(db);
    db.exec('COMMIT');
    return { deleted, protectedCount: remaining.count, referenceData: remaining };
  } catch (error) { db.exec('ROLLBACK'); throw error; }
}
function importReferenceData(source, target, sourceCompany, batchId) {
  const columns = source.prepare('PRAGMA table_info(records)').all().map(r => r.name);
  const targetColumns = target.prepare('PRAGMA table_info(records)').all().map(r => r.name);
  if (JSON.stringify(columns) !== JSON.stringify(targetColumns)) throw new Error('Record schemas differ');
  const rows = source.prepare('SELECT * FROM records ORDER BY id').all();
  target.exec('BEGIN IMMEDIATE');
  try {
    target.exec(`CREATE TABLE IF NOT EXISTS ${TABLE} (
      record_id INTEGER PRIMARY KEY, batch_id TEXT NOT NULL, source_company TEXT NOT NULL,
      source_record_id INTEGER NOT NULL, baseline_json TEXT NOT NULL, imported_at TEXT NOT NULL,
      UNIQUE(batch_id, source_company, source_record_id))`);
    const tracked = target.prepare(`SELECT 1 FROM ${TABLE} WHERE batch_id=? AND source_company=? AND source_record_id=?`);
    const used = target.prepare('SELECT id FROM records WHERE id=? UNION SELECT id FROM record_tombstones WHERE id=?');
    const insert = target.prepare(`INSERT INTO records (${columns.map(c => '"' + c + '"').join(',')}) VALUES (${columns.map(() => '?').join(',')})`);
    const provenance = target.prepare(`INSERT INTO ${TABLE} VALUES(?,?,?,?,?,?)`);
    let next = Number(target.prepare('SELECT MAX(id) id FROM (SELECT id FROM records UNION SELECT id FROM record_tombstones)').get().id || 30) + 1;
    let imported = 0;
    for (const row of rows) {
      if (tracked.get(batchId, sourceCompany, row.id)) continue;
      const sourceId = row.id;
      if (used.get(row.id, row.id)) {
        while (used.get(next, next)) next++;
        row.id = next++;
      }
      insert.run(...columns.map(c => row[c]));
      provenance.run(row.id, batchId, sourceCompany, sourceId, JSON.stringify(row), new Date().toISOString());
      imported++;
    }
    target.exec('COMMIT');
    return { imported, referenceData: referenceData(target) };
  } catch (error) { target.exec('ROLLBACK'); throw error; }
}
module.exports = { referenceData, clearReferenceData, importReferenceData };
