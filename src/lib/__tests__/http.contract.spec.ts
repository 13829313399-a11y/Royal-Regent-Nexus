import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { it } from 'vitest'

it('preserves the existing http contract', async () => {
  const source = readFileSync(join(process.cwd(), 'src/lib/http.ts'), 'utf8')

  assert.match(source, /withCredentials:\s*true/)
})
