import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const root = join(process.cwd(), 'src/features/injection-scheduling-v2')
const dialogSource = readFileSync(join(root, 'components/ManualDemandDialog.vue'), 'utf8')
const viewSource = readFileSync(join(root, 'InjectionSchedulingV2View.vue'), 'utf8')
const backlogSource = readFileSync(join(root, 'components/BacklogDock.vue'), 'utf8')
const apiSource = readFileSync(join(root, 'api/injectionSchedulingV2Api.ts'), 'utf8')
const storeSource = readFileSync(join(root, 'stores/useInjectionSchedulingV2Store.ts'), 'utf8')

describe('manual planning demand dual entry', () => {
  it('offers a manual demand form independent of an imported order sheet', () => {
    for (const copy of ['新增排期任务', '无需下单表', '搜索共享模具', '计划数量', '加入待排池']) {
      expect(dialogSource).toContain(copy)
    }
    expect(viewSource).toContain('<ManualDemandDialog')
    expect(viewSource).toContain('@click="openManualDemand()"')
    expect(storeSource).toContain('const canCreateDemand = computed')
    expect(storeSource).not.toContain("canCreateDemand = computed(() => Boolean(planningPlan")
  })

  it('supports create, revision-protected update and explicit cancellation', () => {
    expect(apiSource).toContain("http.post('/injection-scheduling/manual-demands'")
    expect(apiSource).toContain('http.patch(`/injection-scheduling/manual-demands/${order.id}`')
    expect(apiSource).toContain('http.post(`/injection-scheduling/manual-demands/${order.id}/cancel`')
    expect(apiSource).toContain('expected_revision: order.revision')
    expect(dialogSource).toContain('取消此需求')
  })

  it('lets shared master data enter a draft without a legacy mold id', () => {
    expect(viewSource).toContain('order.moldId || order.moldDefinitionId')
    expect(backlogSource).toContain('order.moldId || order.moldDefinitionId')
    expect(viewSource).toContain('草案可排 · 发布前补实体')
    expect(dialogSource).toContain('草案可排；发布前再落实实体模具')
  })
})
