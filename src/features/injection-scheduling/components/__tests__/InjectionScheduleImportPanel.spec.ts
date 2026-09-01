import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const panelSource = readFileSync(
  join(process.cwd(), 'src/features/injection-scheduling/components/InjectionScheduleImportPanel.vue'),
  'utf8',
)
const apiSource = readFileSync(join(process.cwd(), 'src/api/injectionScheduling.ts'), 'utf8')

describe('InjectionScheduleImportPanel unified plan template', () => {
  it('downloads the one shared plan template and explains the database boundary', () => {
    expect(panelSource).toContain('UNIFIED_PLAN_V2')
    expect(panelSource).toContain('统一计划表 V2.0')
    expect(panelSource).toContain('下载统一计划表模板')
    expect(panelSource).toContain('华兴、华登、华康A、华康B共用同一份计划表格式')
    expect(panelSource).toContain('机台与模具主数据由系统数据库提供')
    expect(panelSource).toContain('injectionSchedulingApi.downloadUnifiedTemplate(props.factoryId)')
    expect(apiSource).toContain("`${BASE_PATH}/templates/unified-plan`")
    expect(apiSource).toContain("params: { factory_id: factoryId }")
    expect(apiSource).toContain("responseType: 'blob'")
  })
})
