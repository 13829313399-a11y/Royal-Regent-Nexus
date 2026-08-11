import { createPinia, setActivePinia } from 'pinia'
import { describe, expect, it } from 'vitest'
import { schedulingColumns, uploadedPlanFieldCount } from '../composables/useSchedulingColumns'
import {
  createBusinessSchedulingBaselineFixture,
  createStressSchedulingBaselineFixture,
  schedulingBaselineFixtureSeed,
  schedulingBaselineFixtureVersion,
  type SchedulingBaselineFixture,
} from './fixtures/schedulingBaselineFixture'
import { seedSchedulingBaselineStore } from './helpers/seedSchedulingBaselineStore'
import { defaultSchedulingDensity, schedulingDensity } from '../config/schedulingLayout'

function p95(samples: number[]) {
  const sorted = [...samples].sort((left, right) => left - right)
  return sorted[Math.max(0, Math.ceil(sorted.length * 0.95) - 1)] ?? 0
}

function measureStoreFixture(fixture: SchedulingBaselineFixture) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = seedSchedulingBaselineStore(pinia, fixture)
  const materializeStartedAt = performance.now()
  const initialRowCount = store.gridRows.length
  const materializeMs = performance.now() - materializeStartedAt
  const summaryStartedAt = performance.now()
  const machineSummaryCount = store.machineSummaryById.size
  const machineSummaryMaterializeMs = performance.now() - summaryStartedAt
  const searchSamples: number[] = []
  const selectionSamples: number[] = []
  const editSamples: number[] = []

  for (let index = 0; index < 20; index += 1) {
    const searchStartedAt = performance.now()
    store.search = index % 2 === 0 ? `QA-ORDER-${String(index + 1).padStart(5, '0')}` : ''
    void store.gridRows.length
    searchSamples.push(performance.now() - searchStartedAt)

    const selectionStartedAt = performance.now()
    store.selectedTaskId = fixture.tasks[(index * 97) % fixture.tasks.length]!.id
    void store.selectedTask?.id
    selectionSamples.push(performance.now() - selectionStartedAt)
  }
  store.search = ''
  store.sourceMode = 'live'
  for (let index = 0; index < 20; index += 1) {
    const task = fixture.tasks[(index * 97) % fixture.tasks.length]!
    const editStartedAt = performance.now()
    store.stageCellEdit(task.id, 'shiftCompleted', task.reportedQuantity + index + 1)
    editSamples.push(performance.now() - editStartedAt)
  }

  return {
    machineCount: fixture.machines.length,
    taskCount: fixture.tasks.length,
    indexedMachineCount: store.tasksByMachine.size,
    machineSummaryCount,
    initialRowCount,
    storeGridMaterializeMs: Number(materializeMs.toFixed(3)),
    machineSummaryMaterializeMs: Number(machineSummaryMaterializeMs.toFixed(3)),
    searchP95Ms: Number(p95(searchSamples).toFixed(3)),
    selectionP95Ms: Number(p95(selectionSamples).toFixed(3)),
    editP95Ms: Number(p95(editSamples).toFixed(3)),
  }
}

describe('B0 repeatable performance baseline', () => {
  it('measures deidentified business and stress fixtures without writing formal data', async () => {
    const businessFixtureStartedAt = performance.now()
    const businessFixture = createBusinessSchedulingBaselineFixture()
    const businessFixtureGenerationMs = performance.now() - businessFixtureStartedAt
    const stressFixtureStartedAt = performance.now()
    const stressFixture = createStressSchedulingBaselineFixture()
    const stressFixtureGenerationMs = performance.now() - stressFixtureStartedAt

    const plannerColumns = schedulingColumns.filter((column) => column.presets.includes('planner'))
    const fullColumns = schedulingColumns.filter((column) => column.presets.includes('full'))
    const frozenPlannerColumns = plannerColumns.filter((column) => column.frozen)
    const result = {
      schemaVersion: 1,
      measuredAt: new Date().toISOString(),
      runtime: {
        vitestEnvironment: 'jsdom',
      },
      fixture: {
        version: schedulingBaselineFixtureVersion,
        seed: schedulingBaselineFixtureSeed,
        containsProductionData: false,
        businessGenerationMs: Number(businessFixtureGenerationMs.toFixed(3)),
        stressGenerationMs: Number(stressFixtureGenerationMs.toFixed(3)),
      },
      currentLayout: {
        plannerColumnCount: plannerColumns.length,
        fullColumnCount: fullColumns.length,
        uploadedPlanFieldCount,
        frozenPlannerKeys: frozenPlannerColumns.map((column) => column.key),
        frozenPlannerWidthPx: frozenPlannerColumns.reduce((total, column) => total + column.width, 0),
        plannerWidthPx: plannerColumns.reduce((total, column) => total + column.width, 0),
        density: defaultSchedulingDensity,
        machineRowEstimatePx: schedulingDensity[defaultSchedulingDensity].machineRow,
        taskRowEstimatePx: schedulingDensity[defaultSchedulingDensity].taskRow,
        virtualizerOverscan: 12,
      },
      measurements: {
        business: measureStoreFixture(businessFixture),
        stress: measureStoreFixture(stressFixture),
      },
      notes: [
        'performance.now() results are machine-local B0 comparison evidence, not a cross-device SLA',
        'browser scrolling, long-task and heap evidence is recorded separately by the manual browser route',
      ],
    }

    expect(result.fixture.containsProductionData).toBe(false)
    expect(result.measurements.business).toMatchObject({ machineCount: 76, taskCount: 1_500, indexedMachineCount: 76, machineSummaryCount: 76, initialRowCount: 1_576 })
    expect(result.measurements.stress).toMatchObject({ machineCount: 120, taskCount: 5_000, indexedMachineCount: 120, machineSummaryCount: 120, initialRowCount: 5_120 })
    expect(result.currentLayout).toMatchObject({ plannerColumnCount: 16, fullColumnCount: 50, uploadedPlanFieldCount: 43, frozenPlannerWidthPx: 554, density: 'comfortable', machineRowEstimatePx: 48, taskRowEstimatePx: 44 })

    console.info(`B0_BASELINE ${JSON.stringify(result)}`)
  }, 30_000)
})
