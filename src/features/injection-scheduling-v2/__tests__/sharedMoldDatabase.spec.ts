import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const featureSource = readFileSync(join(process.cwd(), 'src/features/injection-scheduling-v2/SharedMoldDatabaseView.vue'), 'utf8')
const featureStyles = readFileSync(join(process.cwd(), 'src/features/injection-scheduling-v2/shared-mold-database.css'), 'utf8')
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

  it('uses compact command zones for factory, search and navigation controls', () => {
    expect(featureSource).toContain('data-command-zone="context"')
    expect(featureSource).toMatch(/data-command-zone="context"[\s\S]*class="command-field factory-field"/)
    expect(featureSource).toContain('data-command-zone="search"')
    expect(featureSource).toContain('aria-label="搜索共享模具"')
    expect(featureSource).toMatch(/data-command-zone="actions"[\s\S]*返回排产[\s\S]*厂区机台库[\s\S]*刷新数据[\s\S]*新增模具提案/)
    expect(featureStyles).toMatch(/\.shared-mold-database \.mold-commandbar \.command-context \.page-identity\s*\{[^}]*min-width:\s*188px/)
    expect(featureStyles).toMatch(/\.shared-mold-database \.mold-commandbar \.command-center \.command-search\s*\{[^}]*max-width:\s*none/)
    expect(featureStyles).toMatch(/\.shared-mold-database \.mold-commandbar \.command-actions\s*\{[^}]*white-space:\s*nowrap/)
  })
})
