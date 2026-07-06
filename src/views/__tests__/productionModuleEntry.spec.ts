import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const enterpriseSource = readFileSync(join(process.cwd(), 'src/data/enterpriseMock.ts'), 'utf8')
const moduleCenterSource = readFileSync(join(process.cwd(), 'src/views/ModuleCenterView.vue'), 'utf8')
const routerSource = readFileSync(join(process.cwd(), 'src/router/index.ts'), 'utf8')

describe('production module entry', () => {
  it('keeps the molding sample production task wired to the real task page', () => {
    expect(enterpriseSource).toMatch(/id: 'molding-sample-production-task'/)
    expect(enterpriseSource).toMatch(/title: '啤办生产任务单'/)
    expect(enterpriseSource).toMatch(/接收工程啤办单通知、啤机执行、用料费用回填、完成回传/)
    expect(enterpriseSource).toMatch(/route: '\/modules\/production\/molding-sample-tasks'/)
    expect(enterpriseSource).not.toMatch(/啤机外发协同/)
    expect(enterpriseSource).not.toMatch(/\/pi-outsource\//)

    expect(moduleCenterSource).toMatch(/module\.id === 'molding-sample-production-task'/)
    expect(moduleCenterSource).toMatch(/\/modules\/production\/molding-sample-tasks\?factory=/)
    expect(moduleCenterSource).not.toMatch(/moldingSampleWorkflowMock/)
    expect(moduleCenterSource).not.toMatch(/getMoldingSampleProductionTaskStats/)

    expect(routerSource).toMatch(/path: '\/modules\/production\/molding-sample-tasks'/)
    expect(routerSource).toMatch(/name: 'molding-sample-production-tasks'/)
    expect(routerSource).toMatch(/MoldingSampleProductionTaskView\.vue/)
  })

  it('shows business flow labels on online module cards instead of implementation flags', () => {
    for (const businessCopy of [
      '工程开单后流转到生产任务',
      '主管审核后进入任务队列',
      '工程登记',
      '主管审核',
      '生产回传',
      '审核通知',
      '用料回填',
      '工程同步',
    ]) {
      expect(moduleCenterSource).toMatch(new RegExp(businessCopy))
    }

    expect(moduleCenterSource).not.toMatch(/正式接口|显错|不兜底|不离线/)
  })
})
