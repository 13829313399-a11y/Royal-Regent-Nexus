import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const featureSource = readFileSync(join(process.cwd(), 'src/features/injection-scheduling-v2/SharedMoldDatabaseView.vue'), 'utf8')
const apiSource = readFileSync(join(process.cwd(), 'src/features/injection-scheduling-v2/api/injectionSchedulingV2Api.ts'), 'utf8')
const commandSource = readFileSync(join(process.cwd(), 'src/features/injection-scheduling-v2/components/SchedulingCommandBar.vue'), 'utf8')
const routerSource = readFileSync(join(process.cwd(), 'src/router/index.ts'), 'utf8')

describe('shared mold database workspace', () => {
  it('registers a protected mold database route and a scheduling entry', () => {
    expect(routerSource).toMatch(/path: '\/modules\/production\/injection-scheduling\/mold-database'/)
    expect(routerSource).toMatch(/name: 'injection-scheduling-mold-database'/)
    expect(routerSource).toMatch(/permissions: \['shared_mold:read'\]/)
    expect(commandSource).toContain("openMasterData: []")
    expect(commandSource).toContain("emit('openMasterData')")
    expect(commandSource).toContain('打开共享模具数据库')
  })

  it('provides catalog, detail, factory readiness and proposal interactions', () => {
    for (const copy of [
      '共享模具目录',
      '查看详情',
      '新增模具提案',
      '厂区机安能力',
      '人民币单价（每啤）',
      '提交治理提案',
      '提案人不能审核自己的提案',
    ]) expect(featureSource).toContain(copy)

    expect(featureSource).toContain('listSharedMoldCatalog')
    expect(featureSource).toContain('getSharedMoldDetail')
    expect(featureSource).toContain('createSharedMoldProposal')
    expect(featureSource).toContain("canScoped('shared_mold:propose')")
    expect(featureSource).toContain("canScoped('shared_mold_price:propose')")
    expect(featureSource).toContain("canScoped('factory_mold_capability:manage')")
  })

  it('maps the dedicated backend endpoints without changing the legacy list contract', () => {
    expect(apiSource).toContain("'/injection-scheduling/shared-molds/catalog'")
    expect(apiSource).toContain('`/injection-scheduling/shared-molds/catalog/${definitionId}`')
    expect(apiSource).toContain("'/injection-scheduling/shared-molds/proposals'")
    expect(apiSource).not.toContain("http.get('/injection-scheduling/shared-molds/definitions'")
  })
})
