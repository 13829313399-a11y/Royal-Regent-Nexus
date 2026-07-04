import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const source = readFileSync(join(process.cwd(), 'src/stores/app.ts'), 'utf8')

assert.match(source, /activeFactoryId:\s*'huaxing'/)
assert.match(source, /factory\.id === 'huaxing'/)
assert.doesNotMatch(source, /factory\.id === 'huakang-a'/)
