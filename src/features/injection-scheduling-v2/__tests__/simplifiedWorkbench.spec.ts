import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { buildPasteChanges, formatWorkbenchCell, workbenchColumnPresets } from '../workbench/columns'
import { dueSlackPresentation, formatAClass, priorityPresentation } from '../workbench/presentation'
import type { ImportBatchRecord } from '../types'
import type { WorkbenchCellChange, WorkbenchJob, WorkbenchSnapshot } from '../workbench/types'

const httpMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/lib/http', () => ({ http: httpMocks }))

import { applyWorkbenchImportMapping, fetchWorkbench, moveWorkbenchJob, saveWorkbenchChanges } from '../workbench/api'

function job(index: number): WorkbenchJob {
  return {
    id: `task-${index}`, factoryId: 'huaxing', planId: 'plan-1', taskId: `task-${index}`,
    orderId: `order-${index}`, machineId: 'machine-1', machineCode: '12A-01', sequenceNo: index,
    status: 'PLANNED', orderNo: `SO-${index}`, itemNo: `000${index}`, productName: '脱敏产品',
    warehouseText: 'A仓', setQuantity: null, orderQuantity: 1000, openingCompletedQuantity: 0,
    reportedQuantity: 0, completedQuantity: 0, outstandingQuantity: 1000, completionRate: 0,
    moldId: 'mold-1', moldNo: 'M-001', moldName: '脱敏模具', requiredMachineA: 12,
    materialName: 'ABS', sprueRatio: null, colorName: '蓝', colorPowderCode: '', netWeightG: null,
    grossWeightG: null, materialWeightKg: null, unitPrice: null, sprayRequired: null,
    armRequirement: '双臂', fixtureRequirement: '夹具', orderDate: '', deliveryStartDate: '',
    deliveryDueDate: '2026-08-27', priority: 'NORMAL', plannedStart: '2026-08-25T08:00:00',
    plannedFinish: '2026-08-25T20:00:00', estimatedFinish: '', deliverySlackDays: 2,
    shiftTargetQuantity: 500, todayDayQuantity: 0, todayNightQuantity: 0, downtimeMinutes: 0,
    locked: false, manualOverrideReason: '', orderRemark: '', machineRemark: '', parsedConstraintSummary: '',
    suggestionReason: '', materialReadinessStatus: 'ready', moldEnrichmentStatus: 'MATCHED', sourceBatchId: null,
    sourceSheetName: '计划表', sourceRowNumber: index + 4, sourceLineKey: `line-${index}`,
    taskRevision: 1, orderRevision: 1, planRevision: 2, updatedByName: '调度员', updatedAt: '', lineage: {},
  }
}

const emptyResponse = {
  factory_id: 'huaxing', business_date: '2026-08-25', plan_id: 'plan-1', plan_revision: 2,
  rule_revision: 1, plan_mode: 'PLANNING', polling_revision: 9, machines: [], jobs: [],
  summary: { unplanned_count: 0, overdue_count: 0, conflict_count: 0, running_count: 0,
    today_day_quantity: 0, today_night_quantity: 0 },
}

describe('simplified injection scheduling workbench', () => {
  beforeEach(() => vi.clearAllMocks())

  it('provides three stable presets with the first eight columns frozen', () => {
    expect(Object.keys(workbenchColumnPresets)).toEqual(['scheduler', 'reporter', 'full'])
    for (const columns of Object.values(workbenchColumnPresets)) {
      expect(columns.slice(0, 8).every((column) => column.frozen)).toBe(true)
      expect(new Set(columns.map((column) => column.key)).size).toBe(columns.length)
    }
    expect(workbenchColumnPresets.full.length).toBeGreaterThan(35)
  })

  it('maps the five-state workbench status to operator labels', () => {
    const statusColumn = workbenchColumnPresets.scheduler.find((column) => column.key === 'status')!
    expect(formatWorkbenchCell({ ...job(1), status: 'UNPLANNED' }, statusColumn)).toBe('待排')
    expect(formatWorkbenchCell({ ...job(1), status: 'RUNNING' }, statusColumn)).toBe('生产中')
    expect(formatWorkbenchCell({ ...job(1), status: 'DONE' }, statusColumn)).toBe('完成')
  })

  it('presents priority, delivery risk, and machine A class in operator language', () => {
    const priorityColumn = workbenchColumnPresets.scheduler.find((column) => column.key === 'priority')!
    const slackColumn = workbenchColumnPresets.scheduler.find((column) => column.key === 'deliverySlackDays')!
    const aClassColumn = workbenchColumnPresets.scheduler.find((column) => column.key === 'requiredMachineA')!
    expect(formatWorkbenchCell({ ...job(1), priority: 'CRITICAL' }, priorityColumn)).toBe('特急')
    expect(formatWorkbenchCell({ ...job(1), deliverySlackDays: -2 }, slackColumn)).toBe('逾期 2 天')
    expect(formatWorkbenchCell(job(1), aClassColumn)).toBe('12A')
    expect(priorityPresentation('URGENT').tone).toBe('amber')
    expect(dueSlackPresentation(0).label).toBe('今日到期')
    expect(formatAClass(null)).toBe('A级待补')
  })

  it('keeps the polished shell accessible and exposes only one primary header action', () => {
    const source = readFileSync(join(process.cwd(), 'src/features/injection-scheduling-v2/workbench/InjectionSchedulingWorkbenchView.vue'), 'utf8')
    expect(source).toContain('role="tablist"')
    expect(source).toContain(':aria-selected="view === \'sheet\'"')
    expect(source).toContain('@keydown.esc="clearSearch"')
    expect(source).toContain('<AccountMenu variant="obsidian" compact />')
    expect(source.match(/variant="primary"/g)).toHaveLength(1)
    expect(source).toContain('排期建议')
  })

  it('scopes reduced motion and keeps grid virtualization synchronized to 38 pixels', () => {
    const motion = readFileSync(join(process.cwd(), 'src/features/injection-scheduling-v2/workbench/workbench.motion.css'), 'utf8')
    const grid = readFileSync(join(process.cwd(), 'src/features/injection-scheduling-v2/workbench/WorkbenchGrid.vue'), 'utf8')
    expect(motion).toContain('@media (prefers-reduced-motion: reduce)')
    expect(motion).toContain('.injection-workbench *')
    expect(grid).toContain('estimateSize: () => 38')
  })

  it('keeps dialog confirmation guarded and exposes explicit staged feedback', () => {
    const root = join(process.cwd(), 'src/features/injection-scheduling-v2/workbench')
    const schedule = readFileSync(join(root, 'ScheduleSuggestionDialog.vue'), 'utf8')
    const importDialog = readFileSync(join(root, 'SimpleImportDialog.vue'), 'utf8')
    expect(schedule).toContain(':disabled="!canApply"')
    expect(schedule).toContain('暂不能生成或应用新的排期建议')
    expect(importDialog).toContain('wb-import-rail')
    expect(importDialog).toContain('源文件始终只读')
    expect(importDialog).toContain('role="alert"')
  })

  it('does not treat a letter T in business identifiers as a datetime separator', () => {
    const itemColumn = workbenchColumnPresets.scheduler.find((column) => column.key === 'itemNo')!
    const datetimeColumn = workbenchColumnPresets.scheduler.find((column) => column.key === 'plannedStart')!
    expect(formatWorkbenchCell({ ...job(1), itemNo: 'STYLE-01' }, itemColumn)).toBe('STYLE-01')
    expect(formatWorkbenchCell(job(1), datetimeColumn)).toBe('2026-08-25 08:00:00')
  })

  it('turns a 20 by 10 Excel paste into one atomic bulk request', async () => {
    const rows = Array.from({ length: 20 }, (_, index) => job(index))
    const clipboard = Array.from({ length: 20 }, () => Array.from({ length: 10 }, () => '已排').join('\t')).join('\n')
    const changes = buildPasteChanges(rows, workbenchColumnPresets.scheduler, 0, 0, clipboard)
    expect(changes).toHaveLength(20)
    httpMocks.post.mockResolvedValue({ data: emptyResponse })
    await saveWorkbenchChanges('huaxing', 2, changes)
    expect(httpMocks.post).toHaveBeenCalledTimes(1)
    expect(httpMocks.post.mock.calls[0]?.[0]).toBe('/injection-scheduling/workbench/jobs/bulk-update')
    expect(httpMocks.post.mock.calls[0]?.[1].changes).toHaveLength(20)
  })

  it('keeps 200 staged cells inside a single allowed request', async () => {
    const changes: WorkbenchCellChange[] = Array.from({ length: 200 }, (_, index) => ({
      jobId: `task-${index}`, expectedTaskRevision: 1, expectedOrderRevision: 1,
      field: 'shiftTargetQuantity', value: 500 + index,
    }))
    httpMocks.post.mockResolvedValue({ data: emptyResponse })
    await saveWorkbenchChanges('huaxing', 2, changes)
    expect(httpMocks.post).toHaveBeenCalledTimes(1)
    expect(httpMocks.post.mock.calls[0]?.[1].changes).toHaveLength(200)
  })

  it('preserves the requested same-machine queue position in a move request', async () => {
    httpMocks.post.mockResolvedValue({ data: {} })
    const snapshot = {
      factoryId: 'huaxing', planId: 'plan-1', planRevision: 2, ruleRevision: 1,
    } as WorkbenchSnapshot
    await moveWorkbenchJob(snapshot, job(2), 'machine-1', 0)
    expect(httpMocks.post.mock.calls[0]?.[1].moves[0]).toMatchObject({
      task_id: 'task-2', machine_id: 'machine-1', sequence_no: 0,
    })
    const queueBoard = readFileSync(join(process.cwd(), 'src/features/injection-scheduling-v2/workbench/MachineQueueBoard.vue'), 'utf8')
    expect(queueBoard).toContain('@drop.prevent.stop="drop(machine.id, index)"')
  })

  it('maps the authoritative workbench adapter response without losing leading zero item numbers', async () => {
    httpMocks.get.mockResolvedValue({ data: { ...emptyResponse, jobs: [{
      id: 'backlog:1', factory_id: 'huaxing', plan_id: null, task_id: null, order_id: '1', machine_id: null,
      machine_code: '', sequence_no: null, status: 'UNPLANNED', order_no: 'SO-1', item_no: '000123',
      product_name: '脱敏产品', warehouse_text: '', order_quantity: 10, opening_completed_quantity: 0,
      reported_quantity: 0, completed_quantity: 0, outstanding_quantity: 10, completion_rate: 0,
      mold_id: null, mold_no: '', mold_name: '', material_name: '', color_name: '', color_powder_code: '',
      arm_requirement: '', fixture_requirement: '', order_date: '', delivery_start_date: '', delivery_due_date: '',
      priority: '', planned_start: '', planned_finish: '', estimated_finish: '', shift_target_quantity: 0,
      today_day_quantity: 0, today_night_quantity: 0, downtime_minutes: 0, locked: false,
      manual_override_reason: '', order_remark: '', machine_remark: '', parsed_constraint_summary: '',
      suggestion_reason: '', material_readiness_status: '', mold_enrichment_status: '', source_batch_id: null,
      source_sheet_name: '', source_row_number: null, source_line_key: '', task_revision: null,
      order_revision: 1, plan_revision: null, updated_by_name: '', updated_at: '', lineage: {},
    }] } })
    const result = await fetchWorkbench('huaxing')
    expect(result.jobs[0]?.itemNo).toBe('000123')
    expect(result.jobs[0]?.taskId).toBeNull()
    expect(result.jobs[0]?.status).toBe('UNPLANNED')
  })

  it('saves corrected mappings through the simplified factory-template contract', async () => {
    httpMocks.post.mockResolvedValue({ data: {} })
    await applyWorkbenchImportMapping(
      'huaxing',
      { id: 'batch-1', revision: 3 } as ImportBatchRecord,
      { order_quantity: '订单数量新口径' },
    )
    expect(httpMocks.post.mock.calls[0]?.[0]).toBe('/injection-scheduling/workbench/imports/batch-1/apply-mapping')
    expect(httpMocks.post.mock.calls[0]?.[1]).toMatchObject({
      factory_id: 'huaxing',
      expected_revision: 3,
      mappings: { order_quantity: '订单数量新口径' },
    })
    const dialog = readFileSync(join(process.cwd(), 'src/features/injection-scheduling-v2/workbench/SimpleImportDialog.vue'), 'utf8')
    expect(dialog).toContain('slice(0, 25)')
    expect(dialog).toContain('保存本厂区模板并导入')
  })

  it('switches the formal route to the simplified workbench while retaining the legacy feature as rollback code', () => {
    const root = join(process.cwd(), 'src')
    const routeView = readFileSync(join(root, 'views/InjectionSchedulingV2View.vue'), 'utf8')
    const legacyView = readFileSync(join(root, 'features/injection-scheduling-v2/InjectionSchedulingV2View.vue'), 'utf8')
    expect(routeView).toContain('InjectionSchedulingWorkbenchView')
    expect(routeView).not.toContain("import InjectionSchedulingV2View")
    expect(legacyView).toContain('MachinePlanGrid')
  })
})
