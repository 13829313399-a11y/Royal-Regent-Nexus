// @vitest-environment node
import { execFileSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import { join, resolve, sep } from 'node:path'
import { pathToFileURL } from 'node:url'
import { expect, it } from 'vitest'

it('compiles nested checkout sources without traversing dependency junctions or release artifacts', () => {
  const root = process.cwd()
  mkdirSync(join(root, '.tmp'), { recursive: true })
  const fixture = mkdtempSync(join(root, '.tmp/tailwind-sources-'))
  try {
    mkdirSync(join(fixture, 'src'))
    mkdirSync(join(fixture, '.local-dev'))
    writeFileSync(join(fixture, 'src/style.css'), readFileSync(join(root, 'src/style.css')))
    writeFileSync(join(fixture, 'src/Probe.vue'), '<template><div class="flex grid items-center justify-center text-center overflow-x-auto sr-only md:flex min-w-[321px]">probe</div></template>')
    writeFileSync(join(fixture, 'src/runtime.ts'), 'export const extraClass = "gap-7"')
    writeFileSync(join(fixture, 'index.html'), '<div class="max-w-[654px]"></div>')
    writeFileSync(join(fixture, '.local-dev/old-release.html'), '<div class="min-w-[98765px]"></div>')
    symlinkSync(resolve(root, 'node_modules'), join(fixture, 'node_modules'), process.platform === 'win32' ? 'junction' : 'dir')
    const script = pathToFileURL(join(root, 'scripts/check-tailwind-sources.mjs')).href
    const code = `
      import { inspectTailwindSources } from ${JSON.stringify(script)};
      const r = await inspectTailwindSources(process.argv[1]);
      console.log(JSON.stringify({files:r.files, responsive:r.css.includes('.md\\\\:flex'),
        component:r.css.includes('.min-w-\\\\[321px\\\\]'), runtime:r.css.includes('.gap-7'),
        html:r.css.includes('.max-w-\\\\[654px\\\\]'), artifact:r.css.includes('98765'),
        sharedTokens:['--radius-sm:', '--radius-md:', '--radius-lg:'].every(t=>r.css.includes(t))}));
    `
    const result = JSON.parse(execFileSync(process.execPath, ['--input-type=module', '-e', code, fixture], {
      cwd: root, encoding: 'utf8', timeout: 15000, windowsHide: true,
    }))
    expect(result).toMatchObject({ responsive: true, component: true, runtime: true, html: true, artifact: false, sharedTokens: true })
    expect(result.files).toContain('src/runtime.ts')
    expect(result.files).toContain('index.html')
    expect(result.files.every((file: string) => !file.includes('node_modules') && !file.includes('.local-dev'))).toBe(true)
  } finally {
    if (!resolve(fixture).startsWith(resolve(root, '.tmp') + sep)) throw new Error('Unexpected fixture cleanup target')
    rmSync(fixture, { recursive: true, force: true })
  }
}, 20000)
