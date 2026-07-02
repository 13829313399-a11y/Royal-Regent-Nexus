import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const source = readFileSync(join(process.cwd(), 'src/views/MoldingSampleView.vue'), 'utf8')

assert.match(
  source,
  /<div class="xl:sticky xl:top-24 xl:self-start">[\s\S]*<SectionPanel title="单据队列"/,
)

assert.match(
  source,
  /<RouterLink\s+to="\/modules"\s+class="fixed left-4 top-4 z-50[^"]*"/,
)
