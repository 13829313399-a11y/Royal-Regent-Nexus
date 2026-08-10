import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const featureSource = readFileSync(join(process.cwd(), 'src/features/injection-scheduling-v2/MachineDatabaseView.vue'), 'utf8')
const apiSource = readFileSync(join(process.cwd(), 'src/features/injection-scheduling-v2/api/injectionSchedulingV2Api.ts'), 'utf8')
const routerSource = readFileSync(join(process.cwd(), 'src/router/index.ts'), 'utf8')

describe('factory machine database workspace', () => {
  it('registers the factory-scoped machine database route', () => {
    expect(routerSource).toMatch(/path: '\/modules\/production\/injection-scheduling\/machine-database'/)
    expect(routerSource).toMatch(/name: 'injection-scheduling-machine-database'/)
    expect(routerSource).toMatch(/title: '厂区机台数据库'/)
  })

  it('provides list, create and version-protected edit interactions', () => {
    for (const copy of ['厂区机台数据库', '新增机台', '查看 / 编辑', '设备明细', '文员备注', '保存机台资料']) {
      expect(featureSource).toContain(copy)
    }
    expect(featureSource).toContain("authStore.can('injection_scheduling:manage_master'")
    expect(featureSource).toContain('machine.revision')
    expect(apiSource).toContain("http.get('/injection-scheduling/machines'")
    expect(apiSource).toContain("http.post('/injection-scheduling/machines'")
    expect(apiSource).toContain('http.put(`/injection-scheduling/machines/${machine.id}`')
  })

  it('round-trips equipment details and remarks', () => {
    expect(apiSource).toContain('equipment_details: input.equipmentDetails')
    expect(apiSource).toContain('remarks: input.remarks')
    expect(featureSource).toContain("detailText(machine, 'robot_model')")
    expect(featureSource).toContain('form.remarks')
  })
})
