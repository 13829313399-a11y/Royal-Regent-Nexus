import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, rmSync } from 'node:fs'
import { join, resolve, sep } from 'node:path'
import { writeAcceptanceSamples } from '../write-cutting-acceptance-samples.mjs'

function fixture(run) {
  const parent = resolve('.tmp-tests/acceptance-metadata')
  mkdirSync(parent, { recursive: true })
  const dir = mkdtempSync(join(parent, 'utf8-'))
  try { run(join(dir, 'input.json'), join(dir, 'output.json')) }
  finally { assert.ok(dir.startsWith(parent + sep)); rmSync(dir, { recursive: true }) }
}

test('round-trips Chinese metadata as strict UTF-8 and binds the actual release', () => fixture((input, output) => {
  const links = [{ label: '领料签收样本', workspace: 'materials', group: '生产与物料' }]
  writeFileSync(input, JSON.stringify({ release: 'old', links }), 'utf8')
  assert.deepEqual(writeAcceptanceSamples(input, output, 'test-copy-0185'), { release: 'test-copy-0185', links: 1 })
  const text = new TextDecoder('utf-8', { fatal: true }).decode(readFileSync(output))
  assert.deepEqual(JSON.parse(text), { release: 'test-copy-0185', links })
  assert.ok(text.includes('领料签收样本'))
}))

test('rejects invalid UTF-8 without destroying a previous valid output', () => fixture((input, output) => {
  writeFileSync(input, Buffer.from([0x7b, 0x22, 0xc3, 0x28, 0x22, 0x7d]))
  writeFileSync(output, 'preserved', 'utf8')
  assert.throws(() => writeAcceptanceSamples(input, output, 'test-copy'))
  assert.equal(readFileSync(output, 'utf8'), 'preserved')
}))

test('rejects missing releases and malformed navigation before replacement', () => fixture((input, output) => {
  writeFileSync(input, JSON.stringify({ links: 'not a list' }), 'utf8')
  writeFileSync(output, 'preserved', 'utf8')
  assert.throws(() => writeAcceptanceSamples(input, output, ''))
  assert.throws(() => writeAcceptanceSamples(input, output, 'test-copy'))
  assert.equal(readFileSync(output, 'utf8'), 'preserved')
}))
