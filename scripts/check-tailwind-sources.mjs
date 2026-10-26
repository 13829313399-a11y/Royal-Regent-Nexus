import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { dirname, isAbsolute, relative, resolve, sep } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { performance } from 'node:perf_hooks'
import { compile } from '@tailwindcss/node'
import { Scanner } from '@tailwindcss/oxide'

/** Exercise Tailwind's real compiler/scanner, including nested Windows checkouts. */
export async function inspectTailwindSources(root) {
  root = resolve(root)
  const started = performance.now()
  const stylesheet = resolve(root, 'src/style.css')
  const compiler = await compile(await readFile(stylesheet, 'utf8'), {
    base: dirname(stylesheet),
    onDependency() {},
  })
  assert.equal(compiler.root, 'none', 'Tailwind must not auto-scan the checkout root')
  const scanner = new Scanner({ sources: compiler.sources })
  const candidates = scanner.scan()
  const files = scanner.files.map(file => relative(root, file).split(sep).join('/'))
  assert(files.includes('index.html'), 'HTML entrypoint must be scanned')
  assert(files.some(file => file.startsWith('src/')), 'Application sources must be scanned')
  for (const file of files) {
    assert(!isAbsolute(file) && !file.startsWith('../'), `Unexpected external input: ${file}`)
    assert(file === 'index.html' || file.startsWith('src/'), `Unexpected build input: ${file}`)
    assert(!file.split('/').includes('node_modules'), `Dependency traversal: ${file}`)
  }
  const css = compiler.build(candidates)
  for (const token of ['--radius-sm:', '--radius-md:', '--radius-lg:']) {
    assert(css.includes(token), `Missing shared design token: ${token}`)
  }
  for (const selector of ['.flex', '.grid', '.items-center', '.justify-center', '.text-center', '.overflow-x-auto', '.sr-only']) {
    assert(css.includes(`${selector} {`), `Missing application utility: ${selector}`)
  }
  return { files, candidates, css, milliseconds: performance.now() - started }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const root = process.argv[2] ?? resolve(dirname(fileURLToPath(import.meta.url)), '..')
  const result = await inspectTailwindSources(root)
  console.log(JSON.stringify({ root, files: result.files.length, candidates: result.candidates.length, milliseconds: result.milliseconds }))
}
