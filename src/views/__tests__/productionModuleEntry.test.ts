import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const enterpriseSource = readFileSync(join(process.cwd(), 'src/data/enterpriseMock.ts'), 'utf8')
const moduleCenterSource = readFileSync(join(process.cwd(), 'src/views/ModuleCenterView.vue'), 'utf8')
const routerSource = readFileSync(join(process.cwd(), 'src/router/index.ts'), 'utf8')

assert.match(enterpriseSource, /id: 'molding-sample-production-task'/)
assert.match(enterpriseSource, /title: '啤办生产任务单'/)
assert.match(enterpriseSource, /接收工程啤办单通知、啤机执行、用料费用回填、完成回传/)
assert.match(enterpriseSource, /route: '\/modules\/production\/molding-sample-tasks'/)
assert.doesNotMatch(enterpriseSource, /啤机外发协同/)
assert.doesNotMatch(enterpriseSource, /\/pi-outsource\//)

assert.match(moduleCenterSource, /getMoldingSampleProductionTaskStats/)
assert.match(moduleCenterSource, /module\.id === 'molding-sample-production-task'/)
assert.match(moduleCenterSource, /\/modules\/production\/molding-sample-tasks\?factory=/)

assert.match(routerSource, /path: '\/modules\/production\/molding-sample-tasks'/)
assert.match(routerSource, /name: 'molding-sample-production-tasks'/)
assert.match(routerSource, /MoldingSampleProductionTaskView\.vue/)
