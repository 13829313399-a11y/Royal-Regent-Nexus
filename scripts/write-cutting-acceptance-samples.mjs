import { mkdirSync, readFileSync, renameSync, writeFileSync, existsSync, unlinkSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { randomUUID } from 'node:crypto'

/** Acceptance navigation only. UTF-8 is explicit and malformed input is rejected before replacing output. */
export function writeAcceptanceSamples(input, output, release) {
  if (!/^[A-Za-z0-9._-]{1,120}$/.test(release ?? '')) throw new Error('A valid acceptance release is required')
  const text = new TextDecoder('utf-8', { fatal: true }).decode(readFileSync(input))
  const data = JSON.parse(text)
  if (!data || typeof data !== 'object' || !Array.isArray(data.links) || data.links.length > 30) {
    throw new Error('Invalid acceptance navigation metadata')
  }
  const target = resolve(output)
  mkdirSync(dirname(target), { recursive: true })
  const temporary = `${target}.${randomUUID()}.tmp`
  try {
    writeFileSync(temporary, `${JSON.stringify({ ...data, release }, null, 2)}\n`, { encoding: 'utf8', flag: 'wx' })
    renameSync(temporary, target)
  } finally {
    if (existsSync(temporary)) unlinkSync(temporary)
  }
  return { release, links: data.links.length }
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  const [input, output, release] = process.argv.slice(2)
  if (!input || !output) throw new Error('Usage: node scripts/write-cutting-acceptance-samples.mjs <UTF-8 input.json> <output.json> <release>')
  console.log(JSON.stringify(writeAcceptanceSamples(input, output, release)))
}
