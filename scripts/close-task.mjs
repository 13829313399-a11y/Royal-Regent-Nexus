import { execFileSync, spawnSync } from 'node:child_process'
import { createHash, randomUUID } from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

const profiles = {
  docs: ['implementation', 'validation', 'review', 'cross-review'],
  code: ['implementation', 'validation', 'review', 'cross-review'],
  ui: ['implementation', 'validation', 'browser', 'review', 'design-review', 'cross-review'],
  'high-risk': ['implementation', 'validation', 'risk-validation', 'review', 'cross-review'],
  'high-risk-ui': ['implementation', 'validation', 'risk-validation', 'browser', 'review', 'design-review', 'cross-review'],
}
const independent = new Set(['review', 'design-review', 'cross-review'])
const ensure = (ok, message) => { if (!ok) throw new Error(message) }
const sha = value => createHash('sha256').update(value).digest('hex')
const json = value => JSON.stringify(value, null, 2) + '\n'
const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b)
const canonical = value => process.platform === 'win32' ? value.toLowerCase() : value
const now = () => new Date().toISOString()
const exists = p => { try { fs.lstatSync(p); return true } catch (e) { if (e.code === 'ENOENT') return false; throw e } }
const gitEnv = { ...process.env, GIT_OPTIONAL_LOCKS: '0' }
function git(root, ...args) {
  return execFileSync('git', ['-C', root, ...args], {
    encoding: 'utf8', env: gitEnv, maxBuffer: 32 * 1024 * 1024, stdio: ['ignore', 'pipe', 'pipe'],
  })
}
function idCheck(id) {
  ensure(typeof id === 'string' && /^[a-z0-9][a-z0-9-]{0,63}$/.test(id) && !/^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i.test(id), 'Invalid task ID (lowercase ASCII, digits, hyphens; 1–64 characters).')
}
function label(s, name) {
  ensure(typeof s === 'string' && s.trim() === s && s.length > 0 && s.length <= 300 && !/[\u0000-\u001f]/.test(s), 'Invalid ' + name)
}
function relativeFile(p) {
  ensure(typeof p === 'string' && p.length > 0 && !p.includes('\\') && !path.isAbsolute(p) && p.split('/').every(x =>
    x && x !== '.' && x !== '..' && !/[<>:"|?*\u0000-\u001f]/.test(x) && !/[ .]$/.test(x) && !/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(x)), 'Unsafe relative path: ' + p)
  return p
}
function safe(base, rel) {
  let p = base
  for (const part of relativeFile(rel).split('/')) {
    p = path.join(p, part)
    if (exists(p)) ensure(!fs.lstatSync(p).isSymbolicLink(), 'Symlink/junction forbidden: ' + p)
  }
  return p
}
function regular(p) {
  const st = fs.lstatSync(p)
  ensure(st.isFile() && !st.isSymbolicLink() && st.nlink === 1, 'Expected regular file without hardlinks: ' + p)
  return st
}
function digest(p) {
  const before = regular(p), h = createHash('sha256'), fd = fs.openSync(p, 'r'), buf = Buffer.allocUnsafe(128 * 1024)
  try { for (let n; (n = fs.readSync(fd, buf, 0, buf.length, null)) > 0;) h.update(buf.subarray(0, n)) }
  finally { fs.closeSync(fd) }
  const after = regular(p)
  ensure(before.size === after.size && before.mtimeMs === after.mtimeMs && before.ino === after.ino, 'File changed while hashing: ' + p)
  return { sha256: h.digest('hex'), bytes: after.size }
}
function readJson(p) { regular(p); return JSON.parse(fs.readFileSync(p, 'utf8')) }
function saveJson(p, data) {
  const tmp = p + '.tmp-' + randomUUID()
  fs.writeFileSync(tmp, json(data), { flag: 'wx' })
  try { fs.renameSync(tmp, p) } finally { if (exists(tmp)) fs.unlinkSync(tmp) }
}
function locate(cwd) {
  const root = fs.realpathSync(git(cwd, 'rev-parse', '--show-toplevel').trim())
  ensure(canonical(root) === canonical(fs.realpathSync(cwd)), 'Run from the repository root.')
  const common = fs.realpathSync(git(root, 'rev-parse', '--path-format=absolute', '--git-common-dir').trim())
  ensure(path.basename(common) === '.git', 'Expected a normal Git checkout or linked worktree.')
  const primary = path.dirname(common), anchor = fs.realpathSync(path.dirname(primary))
  const archiveRel = ['_archive', path.basename(primary), 'task-lifecycle', sha(canonical(root)).slice(0, 24)].join('/')
  const archive = safe(anchor, archiveRel)
  ensure(!canonical(archive).startsWith(canonical(root) + path.sep), 'Archive must be outside worktree.')
  ensure(!git(root, 'ls-files', '-z', '--', '.task-work'), '.task-work must not contain tracked files.')
  ensure(spawnSync('git', ['-C', root, 'check-ignore', '-q', '--no-index', '--', '.task-work/probe'], { env: gitEnv }).status === 0, '.task-work must be Git ignored.')
  return { root, anchor, archiveRel, stamp: { root, branch: git(root, 'rev-parse', '--abbrev-ref', 'HEAD').trim(), head: git(root, 'rev-parse', 'HEAD').trim() } }
}
function archivePath(repo, id) { return safe(repo.anchor, repo.archiveRel + '/' + id) }
function taskPath(repo, id) { return safe(repo.root, '.task-work/' + id) }
function snapshot(repo) {
  return git(repo.root, 'status', '--porcelain=v1', '-z', '--untracked-files=all', '--no-renames', '--ignore-submodules=none').split('\0').filter(Boolean).map(row => {
    const status = row.slice(0, 2), name = relativeFile(row.slice(3))
    ensure(status === '??' || status[0] === ' ', 'Staged changes/conflicts detected; keep index untouched.')
    const file = safe(repo.root, name)
    return { path: name, status, ...(exists(file) ? digest(file) : { sha256: null, bytes: 0 }) }
  }).sort((a, b) => a.path < b.path ? -1 : a.path > b.path ? 1 : 0)
}
function delta(before, after) {
  const a = new Map(before.map(x => [x.path, x])), b = new Map(after.map(x => [x.path, x]))
  return [...new Set([...a.keys(), ...b.keys()])].filter(k => !equal(a.get(k), b.get(k))).sort()
}
function defaults(profile) {
  ensure(Object.hasOwn(profiles, profile), 'Unknown profile: ' + profile)
  return Object.fromEntries(profiles[profile].map(k => [k, { status: 'NOT_RUN' }]))
}
function lock(repo, id, action) {
  fs.mkdirSync(safe(repo.root, '.task-work/.locks'), { recursive: true })
  const p = safe(repo.root, '.task-work/.locks/' + id)
  try { fs.mkdirSync(p) } catch (e) { ensure(e.code !== 'EEXIST', 'Task lock exists; verify interrupted/concurrent execution: ' + p); throw e }
  try { return action() } finally { fs.rmdirSync(p) }
}
function load(repo, id) {
  const folder = taskPath(repo, id)
  ensure(exists(folder), 'Open task not found: ' + id)
  const file = safe(folder, 'task.json'), t = readJson(file)
  ensure(t.schemaVersion === 1 && t.id === id && t.state === 'OPEN', 'Invalid task manifest.')
  ensure(equal(t.repo, repo.stamp), 'Worktree, branch or HEAD changed; keep evidence and open a new task.')
  ensure(equal(Object.keys(t.checks ?? {}).sort(), Object.keys(defaults(t.profile)).sort()), 'Required gates changed.')
  label(t.owner, 'owner')
  ensure(Array.isArray(t.baseline), 'Missing baseline.')
  return { t, folder, file }
}
function reset(t) { t.candidate = null; t.checks = defaults(t.profile) }
function validateKnowledge(t, scope, current) {
  const k = t.knowledge
  ensure(k && ['UNCHANGED', 'UPDATED'].includes(k.status) && Array.isArray(k.paths), 'Record knowledge decision before sealing.')
  label(k.note, 'knowledge reason')
  ensure(new Set(k.paths).size === k.paths.length, 'Duplicate knowledge path.')
  ensure(k.status === 'UNCHANGED' ? !k.paths.length : k.paths.length > 0, 'Knowledge decision/path mismatch.')
  for (const name of k.paths) {
    relativeFile(name)
    ensure(scope.includes(name) && current.some(x => x.path === name && x.sha256 !== null) && !name.startsWith('docs/archive/'), 'Promoted target must be a changed, existing, versionable non-history file: ' + name)
  }
}
function fingerprint(t, current, scope) {
  validateKnowledge(t, scope, current)
  return sha(JSON.stringify({ repo: t.repo, owner: t.owner, profile: t.profile, baseline: t.baseline, knowledge: t.knowledge, scope, current }))
}
function verify(repo, t) {
  ensure(t.candidate && Array.isArray(t.candidate.scope), 'Seal candidate first.')
  const current = snapshot(repo), scope = delta(t.baseline, current)
  ensure(equal(scope, t.candidate.scope) && fingerprint(t, current, scope) === t.candidate.fingerprint, 'Candidate stale; reseal and revalidate.')
  return t.candidate.fingerprint
}
function evidence(folder, name) {
  relativeFile(name)
  ensure(/^(reports|evidence)\//.test(name), 'Use evidence under reports/ or evidence/.')
  const p = safe(folder, name)
  ensure(exists(p), 'Evidence missing: ' + name)
  const d = digest(p)
  ensure(d.bytes > 0, 'Empty evidence: ' + name)
  return { path: name, ...d }
}
const actorKey = a => a.trim().toLowerCase()
function checkActor(t, key, actor) {
  label(actor, 'actor')
  if (key === 'implementation') ensure(actorKey(actor) === actorKey(t.owner), 'Implementation actor must match owner.')
  if (independent.has(key)) ensure(actorKey(actor) !== actorKey(t.owner), 'Review requires a different actor from implementer.')
  if (key === 'cross-review') for (const prev of ['review', 'design-review']) {
    if (t.checks[prev]?.actor) ensure(actorKey(actor) !== actorKey(t.checks[prev].actor), 'Cross-review requires a different reviewer.')
  }
}
function validatePass(l, key, fp) {
  const c = l.t.checks[key]
  ensure(c.status === 'PASS' && c.candidate === fp, key + ': ' + c.status + ' or stale candidate')
  checkActor(l.t, key, c.actor)
  ensure(Array.isArray(c.evidence) && c.evidence.length > 0, key + ': missing evidence')
  for (const item of c.evidence) ensure(equal(item, evidence(l.folder, item.path)), key + ': evidence changed: ' + item.path)
}
function inventory(folder) {
  const out = []
  function walk(rel = '') {
    const p = rel ? safe(folder, rel) : folder
    for (const e of fs.readdirSync(p, { withFileTypes: true })) {
      const name = rel ? rel + '/' + e.name : e.name, file = safe(folder, name)
      if (e.isDirectory()) { out.push({ path: name, kind: 'dir' }); walk(name) }
      else { ensure(e.isFile(), 'Unsupported task artifact: ' + name); out.push({ path: name, kind: 'file', ...digest(file) }) }
    }
  }
  walk()
  return out.sort((a, b) => a.path < b.path ? -1 : a.path > b.path ? 1 : 0)
}
function activeReferences(repo, id) {
  // A durable file must never depend on the disposable task directory.
  const prefix = '.task-work/' + id
  const result = spawnSync('git', ['-C', repo.root, 'grep', '--untracked', '--exclude-standard', '-I', '-l', '-F',
    '-e', prefix + '/', '-e', prefix + ')', '-e', prefix.replaceAll('/', '\\') + '\\',
    '--', '.', ':!docs/archive/**'], { encoding: 'utf8', env: gitEnv, maxBuffer: 8 * 1024 * 1024 })
  ensure(!result.error && [0, 1].includes(result.status), 'Unable to check active task references.')
  return result.stdout.trim() ? result.stdout.trim().split(/\r?\n/) : []
}
function preview(repo, l) {
  ensure(equal(readJson(l.file), l.t), 'Task manifest changed during inspection.')
  const fp = verify(repo, l.t), blockers = [], usedPaths = new Map()
  for (const key of profiles[l.t.profile]) {
    try {
      validatePass(l, key, fp)
      for (const item of l.t.checks[key].evidence) {
        const p = canonical(item.path), previous = usedPaths.get(p)
        ensure(!previous || (!independent.has(key) && !independent.has(previous)), 'Independent reviews require separate evidence files.')
        usedPaths.set(p, key)
      }
    } catch (e) { blockers.push(e.message) }
  }
  for (const name of activeReferences(repo, l.t.id)) blockers.push('Active file references disposable task: ' + name)
  const archive = archivePath(repo, l.t.id)
  if (exists(archive)) blockers.push('Archive already exists.')
  const result = { id: l.t.id, candidate: fp, scope: l.t.candidate.scope, archive, blockers, files: inventory(l.folder) }
  return { ...result, ready: !blockers.length, planDigest: sha(JSON.stringify(result)) }
}
export function run(cwd, argv) {
  const [cmd, id, ...args] = argv
  idCheck(id)
  const repo = locate(cwd)
  if (cmd === 'close' && (!args.length || equal(args, ['--dry-run']))) return preview(repo, load(repo, id))
  return lock(repo, id, () => {
    const folder = taskPath(repo, id), archive = archivePath(repo, id)
    if (cmd === 'open') {
      ensure(args.length === 2, 'open <id> <profile> <owner>')
      const [profile, owner] = args, checks = defaults(profile)
      label(owner, 'owner')
      ensure(!exists(folder) && !exists(archive), 'Task ID already exists.')
      const baseline = snapshot(repo)
      fs.mkdirSync(folder)
      for (const name of ['inputs', 'reports', 'evidence']) fs.mkdirSync(safe(folder, name))
      const t = { schemaVersion: 1, state: 'OPEN', id, profile, owner, repo: repo.stamp, createdAt: now(), baseline, knowledge: null, candidate: null, checks }
      fs.writeFileSync(safe(folder, 'task.json'), json(t), { flag: 'wx' })
      fs.writeFileSync(safe(folder, 'inputs/PLAN.md'), '# Task plan\n\nPending: user goal, scope, acceptance criteria, risks and references. Task-only document.\n', { flag: 'wx' })
      return { id, folder, profile, requiredChecks: Object.keys(checks), existingDirtyPaths: baseline.length }
    }
    if (cmd === 'restore') {
      ensure(equal(args, ['--apply']), 'restore <id> --apply')
      const receipt = readJson(safe(archive, 'receipt.json')), source = safe(archive, 'task')
      ensure(receipt.schemaVersion === 1 && receipt.state === 'CLOSED' && receipt.id === id && canonical(receipt.repo.root) === canonical(repo.root), 'Archive identity mismatch.')
      ensure(equal(receipt.files, inventory(source)), 'Archive content changed; restore blocked.')
      const target = safe(repo.root, '.task-work/.recovered/' + id)
      ensure(!exists(target), 'Recovered copy already exists.')
      fs.mkdirSync(path.dirname(target), { recursive: true })
      const temp = safe(repo.root, '.task-work/.recovered/.copy-' + randomUUID())
      fs.mkdirSync(temp)
      try {
        for (const item of receipt.files) {
          const p = safe(temp, item.path)
          if (item.kind === 'dir') fs.mkdirSync(p)
          else fs.copyFileSync(safe(source, item.path), p, fs.constants.COPYFILE_EXCL)
        }
        ensure(equal(receipt.files, inventory(temp)), 'Recovery hash mismatch.')
        fs.copyFileSync(safe(archive, 'receipt.json'), safe(temp, 'ARCHIVE_RECEIPT.json'), fs.constants.COPYFILE_EXCL)
        ensure(!exists(target), 'Recovery destination appeared.')
        fs.renameSync(temp, target)
      } catch (e) { throw new Error('Recovery incomplete; original retained, isolated copy: ' + temp + '; ' + e.message) }
      return { id, recovered: target, archive, note: 'Historical copy, not an active task.' }
    }
    const l = load(repo, id), t = l.t
    if (cmd === 'knowledge') {
      const [status, note, ...paths] = args
      ensure(['UNCHANGED', 'UPDATED'].includes(status) && (status === 'UPDATED' ? paths.length > 0 : !paths.length), 'knowledge <id> <UNCHANGED|UPDATED> <reason> [paths...]')
      label(note, 'knowledge reason'); paths.forEach(relativeFile)
      ensure(new Set(paths).size === paths.length, 'Duplicate knowledge path.')
      t.knowledge = { status, note, paths: paths.sort() }; reset(t)
      saveJson(l.file, t)
      return { id, knowledge: t.knowledge }
    }
    if (cmd === 'seal') {
      args.forEach(relativeFile)
      const current = snapshot(repo), scope = delta(t.baseline, current)
      ensure(equal(args.sort(), scope), 'Declared scope differs from actual changes: ' + JSON.stringify(scope))
      ensure(scope.length || t.profile === 'docs', 'No changed paths (only docs profile permits read-only audit).')
      t.candidate = { scope, fingerprint: fingerprint(t, current, scope), sealedAt: now() }
      t.checks = defaults(t.profile); saveJson(l.file, t)
      return { id, ...t.candidate, requiredChecks: Object.keys(t.checks) }
    }
    if (cmd === 'record') {
      const [key, status, actor, ...paths] = args, keys = profiles[t.profile], index = keys.indexOf(key)
      ensure(index >= 0 && ['PASS', 'FAIL', 'BLOCKED'].includes(status) && paths.length && new Set(paths).size === paths.length, 'record <id> <check> <PASS|FAIL|BLOCKED> <actor> <evidence paths...>')
      const fp = verify(repo, t); checkActor(t, key, actor)
      if (status === 'PASS') for (const prev of keys.slice(0, index)) validatePass(l, prev, fp)
      t.checks[key] = { status, actor, candidate: fp, evidence: paths.map(p => evidence(folder, p)), recordedAt: now() }
      for (const later of keys.slice(index + 1)) t.checks[later] = { status: 'NOT_RUN' }
      saveJson(l.file, t)
      return { id, key, status, candidate: fp }
    }
    if (cmd === 'close') {
      ensure(args.length === 3 && args[0] === '--apply' && args[1] === '--expect' && /^[a-f0-9]{64}$/.test(args[2]), 'Preview first; close <id> --apply --expect <planDigest>')
      const plan = preview(repo, l)
      ensure(plan.ready, 'Close blocked: ' + plan.blockers.join('; '))
      ensure(plan.planDigest === args[2], 'Plan changed; preview again.')
      fs.mkdirSync(path.dirname(archive), { recursive: true })
      ensure(preview(repo, l).planDigest === plan.planDigest, 'Task changed during close.')
      fs.mkdirSync(archive)
      const receipt = safe(archive, 'receipt.json')
      try {
        fs.writeFileSync(receipt, json({ schemaVersion: 1, state: 'CLOSED', id, closedAt: now(), repo: repo.stamp, candidate: plan.candidate, planDigest: plan.planDigest, files: plan.files }), { flag: 'wx' })
        fs.renameSync(folder, safe(archive, 'task'))
      } catch (e) {
        if (exists(receipt)) fs.unlinkSync(receipt)
        fs.rmdirSync(archive)
        throw e
      }
      return { id, state: 'CLOSED', archive, candidate: plan.candidate, files: plan.files.length }
    }
    throw new Error('Unknown command. See docs/agent-routing/task-lifecycle.md.')
  })
}
if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  try {
    const result = run(process.cwd(), process.argv.slice(2))
    console.log(json(result).trimEnd())
    if (result.ready === false) process.exitCode = 2
  } catch (e) { console.error('Task lifecycle blocked: ' + e.message); process.exitCode = 1 }
}
