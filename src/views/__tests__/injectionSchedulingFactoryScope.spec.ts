import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, type Component } from 'vue'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import type { InjectionScheduleImportPreview } from '@/types/injectionSchedule'
import InjectionSchedulingView from '../InjectionSchedulingView.vue'

const injectionScheduleApiMock = vi.hoisted(() => ({
  importDailySchedule: vi.fn(),
}))

vi.mock('@/api/injectionSchedule', () => ({
  injectionScheduleApi: injectionScheduleApiMock,
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    can: () => true,
    hasFactoryScope: () => true,
  }),
}))

interface MountedView {
  router: Router
  wrapper: VueWrapper
}

const mountedViews: MountedView[] = []

function createPreview(
  factoryId: 'huakang-c' | 'huakang-d',
  sourceFileName: string,
  batchId: string,
): InjectionScheduleImportPreview {
  return {
    batch_id: batchId,
    factory_id: factoryId,
    source_file_name: sourceFileName,
    business_date: '2026-07-20',
    status: 'preview',
    summary: {
      machine_count: 1,
      old_machine_count: 1,
      new_machine_count: 0,
      task_count: 1,
      scheduled_task_count: 1,
      pending_task_count: 0,
      relative_task_count: 0,
      no_plan_task_count: 0,
      total_shortage_qty: 123,
      overdue_count: 0,
      missing_due_count: 0,
      negative_or_zero_shortage_count: 0,
      huge_negative_gap_count: 0,
      external_formula_risk_count: 0,
      date_axis_days: 1,
      date_axis_shift_columns: 2,
      business_date: '2026-07-20',
    },
    machines: [],
    tasks: [],
    issues: [],
  }
}

async function mountView(
  factoryId: 'huakang-c' | 'huakang-d',
  section = 'machine-overview',
): Promise<MountedView> {
  const pinia = createPinia()
  setActivePinia(pinia)

  const emptyPage: Component = { template: '<div />' }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/modules/production', component: emptyPage },
      { path: '/modules/production/injection-scheduling', component: InjectionSchedulingView },
    ],
  })

  await router.push({
    path: '/modules/production/injection-scheduling',
    query: { factory: factoryId, section },
  })
  await router.isReady()

  const wrapper = mount(InjectionSchedulingView, {
    global: {
      plugins: [pinia, router],
      stubs: {
        AccountMenu: true,
      },
    },
  })

  await flushPromises()
  await nextTick()

  const mounted = { router, wrapper }
  mountedViews.push(mounted)
  return mounted
}

async function navigate(
  mounted: MountedView,
  factoryId: 'huakang-c' | 'huakang-d',
  section: string,
) {
  await mounted.router.push({
    path: '/modules/production/injection-scheduling',
    query: { factory: factoryId, section },
  })
  await flushPromises()
  await nextTick()
}

describe('injection scheduling factory scope', () => {
  beforeEach(() => {
    injectionScheduleApiMock.importDailySchedule.mockReset()
  })

  afterEach(() => {
    mountedViews.splice(0).forEach(({ wrapper }) => wrapper.unmount())
  })

  it('keeps Huakang C/D on the shared workbench while showing only their own empty data state', async () => {
    const mounted = await mountView('huakang-c')
    const forbiddenHuaxingReferenceData = [
      '河源华兴',
      '39 台机',
      '118 条排期任务',
      '1,860,805',
      '88 条超期',
      '华兴日排版表',
      'Sheet1',
      'T01-BN328',
      '旧1 – 旧39',
      '共 118 条订单任务',
    ]

    expect(mounted.wrapper.text()).toContain('华康C')
    expect(mounted.wrapper.text()).toContain('尚未接入正式主数据')
    expect(mounted.wrapper.get('.back-link').attributes('href')).toContain('/modules/production?factory=huakang-c')

    for (const section of ['machine-overview', 'excel-import', 'order-pool', 'schedule-board']) {
      await navigate(mounted, 'huakang-c', section)
      const text = mounted.wrapper.text()

      expect(text).toContain('华康C')
      for (const forbiddenText of forbiddenHuaxingReferenceData) {
        expect(text).not.toContain(forbiddenText)
      }
    }

    await navigate(mounted, 'huakang-c', 'excel-import')
    expect(mounted.wrapper.text()).toContain('华康C')
    expect(mounted.wrapper.text()).toContain('华康D')
    expect(mounted.wrapper.text()).toContain('通用同一模板')
    expect(mounted.wrapper.get('.back-link').attributes('href')).toContain('factory=huakang-c')
    expect(mounted.wrapper.get('.back-link').attributes('href')).toContain('section=machine-overview')

    await navigate(mounted, 'huakang-d', 'machine-overview')
    expect(mounted.wrapper.text()).toContain('华康D')
    expect(mounted.wrapper.text()).not.toContain('华康C订单池尚未接入')
    expect(mounted.wrapper.get('.back-link').attributes('href')).toContain('/modules/production?factory=huakang-d')
  })

  it('drops an in-flight Huakang C import preview after switching to Huakang D', async () => {
    let resolveHuakangCPreview!: (preview: InjectionScheduleImportPreview) => void
    injectionScheduleApiMock.importDailySchedule.mockReturnValueOnce(
      new Promise<InjectionScheduleImportPreview>((resolve) => {
        resolveHuakangCPreview = resolve
      }),
    )

    const mounted = await mountView('huakang-c', 'excel-import')
    const input = mounted.wrapper.get('input[type="file"]')
    const file = new File(['huakang-c'], 'huakang-c-private.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    Object.defineProperty(input.element, 'files', {
      configurable: true,
      value: [file],
    })

    await input.trigger('change')
    await nextTick()

    expect(injectionScheduleApiMock.importDailySchedule).toHaveBeenCalledWith(file, 'huakang-c')
    expect(mounted.wrapper.text()).toContain('正在解析日排版表')

    await navigate(mounted, 'huakang-d', 'excel-import')
    expect(mounted.wrapper.text()).toContain('华康D尚未上传本厂日排版表')
    expect(mounted.wrapper.text()).not.toContain('huakang-c-private.xlsx')

    resolveHuakangCPreview(createPreview('huakang-c', 'huakang-c-private.xlsx', 'batch-huakang-c'))
    await flushPromises()
    await nextTick()

    expect(mounted.wrapper.text()).toContain('华康D尚未上传本厂日排版表')
    expect(mounted.wrapper.text()).not.toContain('huakang-c-private.xlsx')
    expect(mounted.wrapper.text()).not.toContain('batch-huakang-c')
  })

  it('rejects an import response whose factory does not match the initiating factory', async () => {
    injectionScheduleApiMock.importDailySchedule.mockResolvedValueOnce(
      createPreview('huakang-c', 'wrong-factory.xlsx', 'batch-wrong-factory'),
    )

    const mounted = await mountView('huakang-d', 'excel-import')
    const input = mounted.wrapper.get('input[type="file"]')
    const file = new File(['huakang-d'], 'huakang-d.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    Object.defineProperty(input.element, 'files', {
      configurable: true,
      value: [file],
    })

    await input.trigger('change')
    await flushPromises()
    await nextTick()

    expect(injectionScheduleApiMock.importDailySchedule).toHaveBeenCalledWith(file, 'huakang-d')
    expect(mounted.wrapper.text()).toContain('导入结果厂区不一致，请重新上传')
    expect(mounted.wrapper.text()).not.toContain('wrong-factory.xlsx')
    expect(mounted.wrapper.text()).not.toContain('batch-wrong-factory')
  })
})
