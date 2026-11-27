import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { run } from './close-task.mjs'

function fixture(t) {
  const parent = fs.mkdtempSync(path.join(os.tmpdir(), 'rr-task-lifecycle-'))
  t.after(() => fs.rmSync(parent, { recursive: true, force: true }))
  const root = path.join(parent, 'repo')
  fs.mkdirSync(root)
  const git = (...args) => execFileSync('git', ['-C', root, ...args], { stdio: ['ignore', 'pipe', 'pipe'], encoding: 'utf8' })
  const write = (name, content) => { const p = path.join(root, name); fs.mkdirSync(path.dirname(p), { recursive: true }); fs.writeFileSync(p, content) }
  const read = name => fs.readFileSync(path.join(root, name), 'utf8')
  git('init', '-q')
  git('config', 'user.name', 'Synthetic Fixture')
  git('config', 'user.email', 'fixture@example.invalid')
  git('config', 'commit.gpgsign', 'false')
  git('config', 'core.hooksPath', path.join(parent, 'no-hooks'))
  write('.gitignore', '/.task-work/\n')
  write('a.txt', 'original')
  write('unrelated.txt', 'original unrelated')
  git('add', '.'); git('commit', '-qm', 'fixture')
  const cli = (...args) => run(root, args), id = 'fixture-task'
  const taskPath = name => '.task-work/' + id + '/' + name
  const task = () => JSON.parse(read(taskPath('task.json')))
  const open = (profile = 'code') => cli('open', id, profile, 'developer')
  const seal = () => { write('a.txt', 'changed'); cli('knowledge', id, 'UNCHANGED', 'No durable contract changed'); return cli('seal', id, 'a.txt') }
  const pass = (key, actor, file = 'reports/' + key + '.md') => {
    write(taskPath(file), 'Synthetic fixture evidence for ' + key)
    return cli('record', id, key, 'PASS', actor, file)
  }
  const all = (profile = 'code') => {
    pass('implementation', 'developer'); pass('validation', 'developer')
    if (profile.includes('high-risk')) pass('risk-validation', 'developer')
    if (profile.includes('ui')) pass('browser', 'developer')
    pass('review', 'reviewer')
    if (profile.includes('ui')) pass('design-review', 'designer')
    pass('cross-review', 'external-reviewer')
  }
  return { parent, root, git, write, read, cli, id, taskPath, task, open, seal, pass, all }
}

test('task closure preserves pre-existing edits; dry run, archive, restore and duplicate protection', t => {
  const f = fixture(t)
  f.write('unrelated.txt', 'pre-existing uncommitted work')
  assert.equal(f.open('ui').existingDirtyPaths, 1)
  f.seal(); f.all('ui')
  const before = f.git('status', '--porcelain'), manifest = f.read(f.taskPath('task.json'))
  const preview = f.cli('close', f.id, '--dry-run')
  assert.equal(preview.ready, true)
  assert.equal(fs.existsSync(preview.archive), false)
  assert.equal(f.read(f.taskPath('task.json')), manifest)
  const closed = f.cli('close', f.id, '--apply', '--expect', preview.planDigest)
  assert.equal(closed.state, 'CLOSED')
  assert.equal(fs.existsSync(path.join(f.root, f.taskPath('task.json'))), false)
  assert.equal(f.read('unrelated.txt'), 'pre-existing uncommitted work')
  assert.equal(f.read('a.txt'), 'changed')
  assert.equal(f.git('status', '--porcelain'), before)
  const receipt = JSON.parse(fs.readFileSync(path.join(closed.archive, 'receipt.json'), 'utf8'))
  assert.equal(receipt.candidate, preview.candidate)
  const recovered = f.cli('restore', f.id, '--apply')
  assert.equal(fs.readFileSync(path.join(recovered.recovered, 'reports/review.md'), 'utf8'), 'Synthetic fixture evidence for review')
  assert.ok(fs.existsSync(path.join(closed.archive, 'task/task.json')))
  assert.throws(() => f.cli('restore', f.id, '--apply'), /already exists/)
  assert.throws(() => f.open(), /already exists/)
})

test('required gates, review independence, evidence and tampered gate list', t => {
  const f = fixture(t); f.open('high-risk-ui'); f.seal()
  assert.equal(f.cli('close', f.id).ready, false)
  assert.throws(() => f.cli('record', f.id, 'implementation', 'PASS', 'developer', 'reports/missing.md'), /missing/i)
  f.pass('implementation', 'developer'); f.pass('validation', 'developer')
  assert.throws(() => f.pass('review', 'developer'), /different/)
  assert.throws(() => f.pass('review', 'reviewer'), /risk-validation/)
  f.pass('risk-validation', 'developer'); f.pass('browser', 'developer'); f.pass('review', 'reviewer'); f.pass('design-review', 'designer')
  assert.throws(() => f.pass('cross-review', 'reviewer'), /different/)
  f.pass('cross-review', 'external')
  const task = f.task(); delete task.checks['risk-validation']; f.write(f.taskPath('task.json'), JSON.stringify(task))
  assert.throws(() => f.cli('close', f.id), /Required gates/)
})

test('stale code, modified evidence, dry-run digest and reseal', t => {
  const f = fixture(t); f.open(); f.seal(); f.all()
  const preview = f.cli('close', f.id)
  f.write(f.taskPath('reports/review.md'), 'modified evidence')
  assert.equal(f.cli('close', f.id).ready, false)
  assert.throws(() => f.cli('close', f.id, '--apply', '--expect', preview.planDigest), /blocked/i)
  f.pass('review', 'reviewer'); f.pass('cross-review', 'external-reviewer')
  assert.throws(() => f.cli('close', f.id, '--apply', '--expect', preview.planDigest), /Plan changed/)
  f.write('a.txt', 'changed again')
  assert.throws(() => f.cli('close', f.id), /stale/)
  f.cli('seal', f.id, 'a.txt')
  assert.equal(f.task().checks.review.status, 'NOT_RUN')
  assert.equal(f.cli('close', f.id).ready, false)
})

test('declared scope includes untracked paths; staged files protected', t => {
  const f = fixture(t); f.open(); f.write('a.txt', 'new'); f.write('new.txt', 'untracked')
  f.cli('knowledge', f.id, 'UPDATED', 'New asset', 'new.txt')
  assert.throws(() => f.cli('seal', f.id, 'a.txt'), /scope differs/)
  assert.deepEqual(f.cli('seal', f.id, 'a.txt', 'new.txt').scope, ['a.txt', 'new.txt'])
  f.git('add', 'new.txt')
  assert.throws(() => f.cli('close', f.id), /Staged/)
  assert.ok(f.git('diff', '--cached', '--name-only').includes('new.txt'))
})

test('deletions, invalid paths, missing promotion and unknown gates', t => {
  const f = fixture(t)
  assert.throws(() => f.cli('open', '../escape', 'docs', 'dev'), /task ID/)
  f.open('docs')
  fs.unlinkSync(path.join(f.root, 'a.txt'))
  f.cli('knowledge', f.id, 'UPDATED', 'Deleted file cannot be promoted', 'a.txt')
  assert.throws(() => f.cli('seal', f.id, 'a.txt'), /changed, existing/)
  f.cli('knowledge', f.id, 'UNCHANGED', 'No new durable fact')
  assert.deepEqual(f.cli('seal', f.id, 'a.txt').scope, ['a.txt'])
  assert.throws(() => f.cli('record', f.id, 'made-up', 'PASS', 'dev', 'reports/a.md'), /record <id>/)
  assert.throws(() => f.cli('record', f.id, 'implementation', 'PASS', 'developer', 'reports/../task.json'), /Unsafe relative path/)
})

test('archive collision and changed HEAD prevent close without altering source', t => {
  const f = fixture(t); f.open(); f.seal(); f.all()
  const p = f.cli('close', f.id)
  fs.mkdirSync(p.archive, { recursive: true })
  assert.equal(f.cli('close', f.id).ready, false)
  fs.rmdirSync(p.archive)
  f.git('commit', '--allow-empty', '-qm', 'new HEAD')
  assert.throws(() => f.cli('close', f.id), /HEAD changed/)
  assert.ok(fs.existsSync(path.join(f.root, f.taskPath('task.json'))))
})

test('FAIL and BLOCKED prevent closure and invalidate later checks', t => {
  const f = fixture(t); f.open(); f.seal(); f.all()
  f.write(f.taskPath('reports/fail.md'), 'Synthetic unresolved defect')
  f.cli('record', f.id, 'review', 'FAIL', 'reviewer', 'reports/fail.md')
  assert.ok(f.cli('close', f.id).blockers.some(x => x.includes('review: FAIL')))
  assert.equal(f.task().checks['cross-review'].status, 'NOT_RUN')
  f.cli('record', f.id, 'review', 'BLOCKED', 'reviewer', 'reports/fail.md')
  assert.equal(f.cli('close', f.id).ready, false)
})

test('rejects symlink/junction artifacts and tampered archives', t => {
  const f = fixture(t); f.open(); f.seal(); f.all()
  const outside = path.join(f.parent, 'outside'); fs.mkdirSync(outside)
  fs.writeFileSync(path.join(outside, 'synthetic.txt'), 'synthetic data')
  const link = path.join(f.root, f.taskPath('evidence/linked'))
  fs.symlinkSync(outside, link, process.platform === 'win32' ? 'junction' : 'dir')
  assert.throws(() => f.cli('close', f.id), /Symlink|junction/)
  fs.unlinkSync(link)
  const p = f.cli('close', f.id)
  const closed = f.cli('close', f.id, '--apply', '--expect', p.planDigest)
  fs.writeFileSync(path.join(closed.archive, 'task/reports/review.md'), 'tampered')
  assert.throws(() => f.cli('restore', f.id, '--apply'), /content changed/)
})

test('independent reviews need separate files; preview is read only', t => {
  const f = fixture(t); f.open(); f.seal(); f.pass('implementation', 'developer'); f.pass('validation', 'developer'); f.pass('review', 'reviewer')
  f.cli('record', f.id, 'cross-review', 'PASS', 'external', 'reports/review.md')
  const p = f.cli('close', f.id)
  assert.equal(p.ready, false)
  assert.ok(p.blockers.some(x => x.includes('separate evidence')))
  assert.equal(fs.existsSync(p.archive), false)
})

test('linked worktrees use separate tasks and archive namespaces', t => {
  const f = fixture(t); f.open(); f.seal(); f.all()
  const other = path.join(f.parent, 'second')
  f.git('worktree', 'add', '-qb', 'second-task', other)
  const otherRun = (...args) => run(other, args)
  otherRun('open', f.id, 'docs', 'developer')
  otherRun('knowledge', f.id, 'UNCHANGED', 'Read only')
  otherRun('seal', f.id)
  assert.notEqual(otherRun('close', f.id).archive, f.cli('close', f.id).archive)
  assert.equal(f.cli('close', f.id).ready, true)
  assert.equal(otherRun('close', f.id).ready, false)
})

test('blocks durable documents that link to the disposable task folder', t => {
  const f = fixture(t); f.open()
  f.write('a.txt', 'Current reference: .task-work/fixture-task/inputs/PLAN.md')
  f.cli('knowledge', f.id, 'UNCHANGED', 'No durable change')
  f.cli('seal', f.id, 'a.txt'); f.all()
  assert.ok(f.cli('close', f.id).blockers.some(x => x.includes('Active file references disposable task')))
})
