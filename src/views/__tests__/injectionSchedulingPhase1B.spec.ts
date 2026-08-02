import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const viewSource = readFileSync(join(process.cwd(), 'src/views/InjectionSchedulingWorkspaceView.vue'), 'utf8')
const storeSource = readFileSync(join(process.cwd(), 'src/stores/injectionScheduling.ts'), 'utf8')
const typeSource = readFileSync(join(process.cwd(), 'src/types/injectionScheduling.ts'), 'utf8')

describe('injection scheduling phase 1B workspace', () => {
  it('incrementally renders the 257-task board and keeps an accessible manual fallback', () => {
    expect(viewSource).toContain('const visibleGroupLimit = ref(12)')
    expect(viewSource).toContain('filteredGroups.value.slice(0, visibleGroupLimit.value)')
    expect(viewSource).toContain('@scroll.passive="loadMoreOnScroll"')
    expect(viewSource).toContain('加载更多机台')
    expect(viewSource).toContain('已增量渲染')
  })

  it('supports sticky identifiers, keyboard search and reduced motion', () => {
    expect(viewSource).toContain("event.key.toLocaleLowerCase() === 'f'")
    expect(viewSource).toContain('ref="searchInput"')
    expect(viewSource).toContain('跳到排程工作区')
    expect(viewSource).toContain('.task-row td:nth-child(3)')
    expect(viewSource).toContain('@media (prefers-reduced-motion: reduce)')
    expect(viewSource).toContain('role="dialog" aria-modal="true"')
  })

  it('keeps full-screen scroll locking scoped to the scheduling workspace', () => {
    expect(viewSource).not.toContain(':global(html)')
    expect(viewSource).not.toContain(':global(body)')
    expect(viewSource).not.toContain(':global(#app)')
    expect(viewSource).toMatch(/\.schedule-shell\s*\{[^}]*min-width:1180px[^}]*overflow:hidden/)
  })

  it('makes density, field groups, empty state and completeness filters interactive', () => {
    expect(viewSource).toContain('toggleDensity')
    expect(viewSource).toContain('columnVisibility.colorMaterial')
    expect(viewSource).toContain('没有符合当前条件的排程任务')
    expect(viewSource).toContain('v-model="dataQuality"')
    expect(storeSource).toContain("dataQuality.value === 'missing'")
    expect(typeSource).toContain("WorkspaceDataQualityFilter = 'all' | 'complete' | 'missing'")
  })

  it('exposes offline, failure and full shift-report states without pretending to publish', () => {
    expect(viewSource).toContain('离线草稿模式')
    expect(viewSource).toContain('role="alert"')
    expect(viewSource).toContain('停机 / 故障时间（小时）')
    expect(viewSource).toContain('异常类型')
    expect(viewSource).toContain('操作')
    expect(typeSource).toContain('downtimeHours: number')
    expect(typeSource).toContain('exceptionType: string')
    expect(viewSource).not.toContain('发布计划</button>')
  })

  it('connects the phase 4 Excel preview and explicit confirmation flow to formal data', () => {
    expect(viewSource).toContain('正式数据库')
    expect(viewSource).toContain('导入注塑排产计划表')
    expect(viewSource).toContain('我已阅读并确认全部')
    expect(viewSource).toContain('确认导入数据库草案')
    expect(viewSource).toContain('阶段 5 匹配校验已启用')
    expect(viewSource).toContain('人工覆盖原因（必填）')
    expect(storeSource).toContain('injectionSchedulingRepository.evaluateBacklogOrder')
    expect(storeSource).toContain('injectionSchedulingRepository.previewImport')
    expect(storeSource).toContain('allBlockingIssuesAcknowledged')
    expect(typeSource).toContain("SchedulingSourceMode = 'mock' | 'live'")
  })
})
