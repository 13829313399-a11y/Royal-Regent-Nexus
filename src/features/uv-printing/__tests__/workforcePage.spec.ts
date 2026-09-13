import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { computed, defineComponent, ref, shallowRef, type Ref } from 'vue'

/**
 * 页面上下文替身只需要 `business_date / shift / scope / scopeFor / can`，
 * 真实 `useUvWorkspace` 依赖路由与账号权限；这里用等价的 ref/函数替身，
 * 但注入的仍然是冻结契约 `UvPageContext` 本身。
 *
 * 只 stub `useRoute` / `useRouter`，其余 vue-router 导出保持真实，
 * 这样 RouterView、RouterLink 在宿主壳层里依旧可用。
 */
vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    useRoute: () => ({ path: '/', name: 'uv-printing-workforce', query: {}, params: {} }),
    useRouter: () => ({ replace: async () => undefined, push: async () => undefined }),
  }
})

import type {
  BusinessDate,
  ShiftCode,
  ShiftScope,
  UvAssignment,
  UvReport,
  UvScope,
  UvWorkerRef,
  UvWorkspaceTransport,
} from '../contracts'
import { UV_PERMISSIONS } from '../contracts'
import { UV_CONTEXT_KEY, UV_TRANSPORT_KEY, type UvPageContext } from '../composables/uvPageContext'
import { addDays } from '../domain/businessTime'
import { decimalCompare, decimalSum, splitRemainder } from '../domain/decimal'
import { UvMemoryStore } from '../preview/memoryStore'
import { SAMPLE_BUSINESS_DATE, SAMPLE_CURRENCY } from '../preview/fixtures'
import WorkforcePage from '../pages/WorkforcePage.vue'

/**
 * 人员班次工作区测试（UV_PRINT_SHARED_SPEC.md 5.6 / 6.7）。
 *
 * 覆盖：分摊余数补最小币种单位（1.00 给三人 = 0.34 + 0.33 + 0.33，合计完全一致）、
 * 无工价报工的「未定价且金额为 null（不是 0）」、质量未判清进待核桶、
 * 「复制前一班」只复制排班计划不改写报工产量、离职员工历史排班与工资快照保留。
 */

const SPLIT_DATE: BusinessDate = '2026-09-10'
const SPLIT_MACHINE = 'DEMO-M01'
/** 夹具里唯一同时具备计件工价与已确认合格量的产品：5 × 0.20 = 1.00 HKD。 */
const SPLIT_PRODUCT = 'DEMO-P-0001'
const SPLIT_PROCESS = 'DEMO-PV-0001'

/** 只读访问样例事实源，用于断言与构造夹具；不新增任何生产代码。 */
interface StoreFacts {
  _reports: UvReport[]
  _assignments: UvAssignment[]
}

function facts(store: UvMemoryStore): StoreFacts {
  return store as unknown as StoreFacts
}

/**
 * 样例事实源只在构造与命令成功后重算派生字段（报工的 commercial / payroll /
 * worker_shares）。测试直接注入夹具后必须显式重算一次，否则 payroll 为空，
 * 会把「有工价」误判成「未定价」。
 */
function recompute(store: UvMemoryStore): void {
  const target = store as unknown as { recomputeDerived?: () => void }
  if (typeof target.recomputeDerived !== 'function') throw new Error('样例 transport 缺少 recomputeDerived')
  target.recomputeDerived()
}

function reportQuantities(store: UvMemoryStore): Record<string, number> {
  const result: Record<string, number> = {}
  for (const item of facts(store)._reports) result[item.id] = item.reported_qty
  return result
}

function assignment(
  id: string,
  businessDate: BusinessDate,
  shift: ShiftCode,
  machineId: string,
  workerId: string,
  note = '',
): UvAssignment {
  return {
    id,
    factory_id: 'huakang-a',
    version: 1,
    created_at: `${businessDate}T00:00:00Z`,
    updated_at: `${businessDate}T00:00:00Z`,
    business_date: businessDate,
    shift,
    machine_id: machineId,
    worker_id: workerId,
    share: 1,
    work_batch: `DEMO-B-${businessDate}-${machineId}`,
    note,
  }
}

function report(seed: Partial<UvReport> & { id: string; worker_ids: string[] }): UvReport {
  const { id, ...rest } = seed
  return {
    factory_id: 'huakang-a',
    version: 1,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    business_date: SPLIT_DATE,
    shift: 'day',
    shift_template_version_id: 'shift-template-v1-day',
    machine_id: SPLIT_MACHINE,
    product_id: SPLIT_PRODUCT,
    process_version_id: SPLIT_PROCESS,
    product_no: 'DEMO-0001',
    product_name: '面板外壳 A',
    source_kind: 'manual',
    status: 'confirmed',
    quality_status: 'complete',
    reported_qty: 0,
    good_qty: 0,
    defective_qty: 0,
    pending_qty: 0,
    semi_finished_qty: 0,
    worker_names: [],
    notes: '',
    replaces_report_id: null,
    correction_reason: '',
    allocation_total: 0,
    ...rest,
    id,
  }
}

/**
 * 工资分摊夹具：2026-09-10 白班 M01 的计件金额正好 1.00 HKD
 * （5 件 × 0.20 计件工价），由 W-005 / W-006 / W-002 三人等分。
 * 稳定员工顺序按工号升序 = E002 / E005 / E006，因此余数补 E002 → 0.34。
 */
function splitStore(): UvMemoryStore {
  const store = new UvMemoryStore()
  const raw = facts(store)
  raw._assignments = raw._assignments.filter(
    (item) => !(item.business_date === SPLIT_DATE && item.shift === 'day' && item.machine_id === SPLIT_MACHINE),
  )
  raw._assignments.push(
    assignment('DEMO-AS-T1', SPLIT_DATE, 'day', SPLIT_MACHINE, 'DEMO-W-002'),
    assignment('DEMO-AS-T2', SPLIT_DATE, 'day', SPLIT_MACHINE, 'DEMO-W-006'),
    assignment('DEMO-AS-T3', SPLIT_DATE, 'day', SPLIT_MACHINE, 'DEMO-W-005'),
  )
  raw._reports = raw._reports.filter(
    (item) => !(item.business_date === SPLIT_DATE && item.machine_id === SPLIT_MACHINE),
  )
  raw._reports.push(
    report({
      id: 'DEMO-R-SPLIT',
      worker_ids: ['DEMO-W-005', 'DEMO-W-002', 'DEMO-W-006'],
      reported_qty: 5,
      good_qty: 5,
      notes: '计件金额 5 × 0.20 = 1.00 HKD，用于验证余数补最小币种单位。',
    }),
  )
  recompute(store)
  return store
}

/** 质量未判清夹具：已确认计件工价、已排班，但合格数为 0（全部待判）。 */
function qualityPendingStore(): UvMemoryStore {
  const store = new UvMemoryStore()
  const raw = facts(store)
  raw._assignments = raw._assignments.filter(
    (item) => !(item.business_date === SPLIT_DATE && item.shift === 'day' && item.machine_id === SPLIT_MACHINE),
  )
  raw._assignments.push(assignment('DEMO-AS-Q1', SPLIT_DATE, 'day', SPLIT_MACHINE, 'DEMO-W-002'))
  raw._reports = raw._reports.filter(
    (item) => !(item.business_date === SPLIT_DATE && item.machine_id === SPLIT_MACHINE),
  )
  raw._reports.push(
    report({
      id: 'DEMO-R-QUALITY',
      worker_ids: ['DEMO-W-002'],
      status: 'draft',
      quality_status: 'pending',
      reported_qty: 10,
      pending_qty: 10,
      notes: '全部待判：质量未判清时不给 0 工资，进待核桶。',
    }),
  )
  recompute(store)
  return store
}

interface Harness {
  transport: Ref<UvWorkspaceTransport>
  context: UvPageContext
  businessDate: Ref<BusinessDate>
  revision: Ref<number>
}

function harness(store: UvMemoryStore, options: { permissions?: string[] } = {}): Harness {
  const businessDate = ref<BusinessDate>(SAMPLE_BUSINESS_DATE)
  const revision = ref(0)
  const permissions = new Set(options.permissions ?? Object.values(UV_PERMISSIONS))
  const transport = shallowRef<UvWorkspaceTransport>(store)
  const can = (permission: string) => permissions.has(permission)
  const shift = computed<ShiftScope>(() => 'all')
  const scope = computed<UvScope>(() => ({ factory_id: 'huakang-a', business_date: businessDate.value }))
  const scopeFor = (overrides: Partial<UvScope> = {}): UvScope => ({ ...scope.value, ...overrides })

  const context = {
    workspace: {
      business_date: businessDate,
      shift,
      scope,
      scopeFor,
      can,
      isReadOnly: computed(() => false),
      isPreview: computed(() => false),
      violation: computed(() => null),
      setBusinessDate: (value: BusinessDate) => { businessDate.value = value },
      setShift: () => undefined,
      setSampleClock: () => undefined,
      sampleAsOf: ref(''),
      workspacePath: '/modules/production/uv-printing',
    },
    transport,
    revision,
    markDirty: () => { revision.value += 1 },
    isPreview: computed(() => false),
  } as unknown as UvPageContext

  return { transport, context, businessDate, revision }
}

const PageStub = defineComponent({ name: 'PageStub', template: '<div />' })

async function testRouter(): Promise<Router> {
  const instance = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', name: 'uv-printing-workforce', component: PageStub }],
  })
  await instance.push('/')
  await instance.isReady()
  return instance
}

async function mountPage(store: UvMemoryStore, options: { permissions?: string[] } = {}) {
  const h = harness(store, options)
  const wrapper = mount(WorkforcePage, {
    attachTo: document.body,
    global: {
      plugins: [await testRouter()],
      provide: {
        [UV_TRANSPORT_KEY as symbol]: h.transport,
        [UV_CONTEXT_KEY as symbol]: h.context,
      },
    },
  })
  await flushPromises()
  return { wrapper, ...h }
}

function cellButton(wrapper: VueWrapper, machineId: string, shift: ShiftCode) {
  return wrapper.get(`button[data-machine-id="${machineId}"][data-shift="${shift}"]`)
}

function buttonByText(wrapper: VueWrapper, text: string) {
  return wrapper.findAll('button').find((button) => button.text().includes(text))
}

function payrollRow(wrapper: VueWrapper, workerId: string) {
  return wrapper.get(`[data-uv="payroll-lines"] tbody tr[data-worker-id="${workerId}"]`)
}

beforeEach(() => {
  setActivePinia(createPinia())
  document.body.innerHTML = ''
  document.body.style.overflow = ''
})

describe('人员班次工作区', () => {
  it('把 1.00 拆成 0.34 + 0.33 + 0.33 并保持合计完全一致', async () => {
    const store = splitStore()
    const { wrapper, businessDate } = await mountPage(store)
    businessDate.value = SPLIT_DATE
    await flushPromises()

    // 领域函数是页面分摊的依据：先证明它本身满足「余数补最小币种单位」。
    const shares = splitRemainder('1.00', 3, SAMPLE_CURRENCY)
    expect(shares).toEqual(['0.34', '0.33', '0.33'])
    expect(decimalSum(shares)).toBe('1')
    expect(decimalCompare(decimalSum(shares), '1.00')).toBe(0)

    const preview = await store.payrollPreview({
      factory_id: 'huakang-a',
      date_from: SPLIT_DATE,
      date_to: SPLIT_DATE,
    })
    expect(preview.data.batch_total?.amount).toBe('1')
    expect(decimalCompare(preview.data.batch_total?.amount ?? '0', '1.00')).toBe(0)
    expect(preview.data.lines.map((line) => line.amount?.amount).sort())
      .toEqual(['0.33', '0.33', '0.34'])
    expect(decimalCompare(
      decimalSum(preview.data.lines.map((line) => line.amount?.amount ?? '0')),
      '1.00',
    )).toBe(0)

    // UI 必须真的呈现这笔分摊明细，而不是只在 store 里算过。
    expect(wrapper.findAll('[data-uv="payroll-lines"] tbody tr')).toHaveLength(3)
    expect(wrapper.text()).toContain('HK$0.34')
    expect(wrapper.text()).toContain('HK$0.33')
    expect(wrapper.text()).toContain('1.00 给三人 = 0.34 + 0.33 + 0.33')

    await payrollRow(wrapper, 'DEMO-W-002').findAll('button').at(-1)!.trigger('click')
    await flushPromises()

    const split = wrapper.get('[data-uv="payroll-split"]')
    expect(split.text()).toContain('批次金额 HK$1.00 ÷ 3 人')
    expect(split.text()).toContain('DEMO 操作员乙（DEMO-E002）：')
    expect(split.text()).toContain('HK$0.34')
    expect(split.text()).toContain('余数补足')
    expect(split.text()).toContain('HK$0.33')
    expect(wrapper.text()).toContain('合计完全一致')

    wrapper.unmount()
  })

  it('无工价报工显示「未定价」且金额为 null，不显示 0 工资', async () => {
    const store = new UvMemoryStore()
    const { wrapper } = await mountPage(store)

    const preview = await store.payrollPreview({
      factory_id: 'huakang-a',
      date_from: SAMPLE_BUSINESS_DATE,
      date_to: SAMPLE_BUSINESS_DATE,
    })
    expect(preview.data.unpriced_reports).toBeGreaterThan(0)
    // 未定价 = 金额缺失（null），不是「0 工资」。
    // 注意：有生效工价但合格数为 0 的报工可以合法地产生 0 金额行，
    // 因此这里断言的是「未定价不能被表示成 0」，即未定价项一律为 null。
    expect(preview.data.lines.every((line) => line.state !== 'unpriced' || line.amount === null)).toBe(true)
    expect(preview.data.warnings.some((warning) => warning.code === 'payroll_unpriced')).toBe(true)

    const payload = (await store.reports({
      factory_id: 'huakang-a',
      business_date: SAMPLE_BUSINESS_DATE,
    })).data.items.map((item) => ({
      id: item.id,
      state: item.payroll?.state ?? 'no-payroll',
      wage: item.payroll?.piece_wage ?? null,
      amount: item.payroll?.amount?.amount ?? null,
      workers: item.worker_ids.length,
    }))
    // DEMO-R-2003（按键铭牌）在夹具里没有生效的计件工价：金额必须是 null，不能是 0。
    const unpriced = payload.find((item) => item.id === 'DEMO-R-2003')
    expect(unpriced?.state).toBe('unpriced')
    expect(unpriced?.wage).toBeNull()
    expect(unpriced?.amount).toBeNull()
    // 未定价与显式 0 工资必须区分：未定价报工绝不下发 0。
    expect(payload.filter((item) => item.state === 'unpriced').every((item) => item.amount === null)).toBe(true)
    // DEMO-R-2005（打样机）没有排班人员：计件金额属于班组，未排班时不进任何个人工资。
    const unassigned = payload.find((item) => item.id === 'DEMO-R-2005')
    expect(unassigned?.workers).toBe(0)

    const pending = wrapper.get('[data-uv="payroll-pending"]')
    expect(pending.text()).toContain('未定价')
    expect(pending.text()).toContain('未排班')
    expect(pending.text()).toContain('没有生效的计件工价')
    expect(wrapper.text()).not.toContain('HK$0.00')

    wrapper.unmount()
  })

  it('质量未判清的报工进入待核桶并说明原因', async () => {
    const store = qualityPendingStore()
    const { wrapper, businessDate } = await mountPage(store)
    businessDate.value = SPLIT_DATE
    await flushPromises()

    const preview = await store.payrollPreview({
      factory_id: 'huakang-a',
      date_from: SPLIT_DATE,
      date_to: SPLIT_DATE,
    })
    expect(preview.data.quality_pending_reports).toBe(1)
    expect(preview.data.batch_total?.amount).toBe('0')
    expect(preview.data.warnings.some((warning) => warning.code === 'payroll_quality')).toBe(true)
    expect(preview.data.coverage).toBe('partial')

    await flushPromises()

    const pending = wrapper.get('[data-uv="payroll-pending"]')
    expect(pending.text()).toContain('待核')
    expect(pending.text()).toContain('质量尚未判清，按已判合格量暂算')
    expect(wrapper.text()).toContain('暂算')
    // 质量未判清时页面必须写明这是暂算口径，而不是把 0.00 当成最终工资。
    expect(wrapper.text()).toContain('按已判合格量暂算')

    wrapper.unmount()
  })

  it('「复制前一班」只复制排班计划，不改写任何报工产量', async () => {
    const store = new UvMemoryStore()
    const { wrapper, revision } = await mountPage(store)

    const quantitiesBefore = reportQuantities(store)
    const reportCountBefore = facts(store)._reports.length
    expect(quantitiesBefore['DEMO-R-2005']).toBe(30)

    // 2026-09-13 白班 M02 在夹具里没有排班：正好用来验证「复制前一班」。
    await cellButton(wrapper, 'DEMO-M02', 'day').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('复制前一班')

    const copyButton = buttonByText(wrapper, '复制前一班')
    expect(copyButton).toBeTruthy()
    await copyButton!.trigger('click')
    await flushPromises()

    // 前一班 = 2026-09-12 夜班 M02，夹具里是 DEMO-W-005 与离职的 DEMO-W-007。
    const applied = wrapper
      .findAll('input[type="checkbox"][data-worker-id]')
      .filter((input) => (input.element as HTMLInputElement).checked)
      .map((input) => input.attributes('data-worker-id'))
    expect(applied).toEqual(expect.arrayContaining(['DEMO-W-005', 'DEMO-W-007']))
    expect(wrapper.text()).toContain('不会复制产量、合格数与工资')

    const saveButton = buttonByText(wrapper, '保存本班排班')
    expect(saveButton).toBeTruthy()
    await saveButton!.trigger('click')
    await flushPromises()

    // 写入成功 → ctx.markDirty() → revision 前进，页面按新排班重新派生。
    expect(revision.value).toBeGreaterThan(0)
    const saved = facts(store)._assignments.filter(
      (item) =>
        item.business_date === SAMPLE_BUSINESS_DATE
        && item.shift === 'day'
        && item.machine_id === 'DEMO-M02',
    )
    expect(saved.map((item) => item.worker_id).sort()).toEqual(['DEMO-W-005', 'DEMO-W-007'])

    // 报工数量一条都不能变。
    expect(reportQuantities(store)).toEqual(quantitiesBefore)
    expect(facts(store)._reports.length).toBe(reportCountBefore)

    const preview = await store.payrollPreview({
      factory_id: 'huakang-a',
      date_from: SAMPLE_BUSINESS_DATE,
      date_to: SAMPLE_BUSINESS_DATE,
    })
    expect(preview.data.lines.some((line) => line.worker_id === 'DEMO-W-005')).toBe(true)

    wrapper.unmount()
  })

  it('离职员工的历史排班与工资快照保留', async () => {
    const store = new UvMemoryStore()
    const { wrapper, businessDate } = await mountPage(store)

    const holiday = addDays(SAMPLE_BUSINESS_DATE, -1)
    businessDate.value = holiday
    await flushPromises()

    const workers = await store.workers({ factory_id: 'huakang-a' })
    const departedRef: UvWorkerRef | undefined = workers.data.items.find((worker) => worker.id === 'DEMO-W-007')
    expect(departedRef?.employ_state).toBe('left')
    expect(departedRef?.left_on).toBe('2026-08-31')

    const assignments = await store.assignments({
      factory_id: 'huakang-a',
      business_date: holiday,
      shift: 'night',
    })
    expect(assignments.data.items.some((item) => item.worker_id === 'DEMO-W-007')).toBe(true)

    // 历史班次仍然渲染在矩阵里，并标注为已离职。
    expect(wrapper.text()).toContain('DEMO 离职师傅庚')
    expect(wrapper.text()).toContain('已离职')

    // 历史工资快照保留：09-12 夜班 14 件 × 0.35 = 4.90，由 2 人均分。
    const preview = await store.payrollPreview({
      factory_id: 'huakang-a',
      date_from: holiday,
      date_to: holiday,
    })
    const departedLine = preview.data.lines.find((line) => line.worker_id === 'DEMO-W-007')
    expect(departedLine?.worker_name).toBe('DEMO 离职师傅庚')
    expect(departedLine?.amount?.amount).toBe('2.45')
    expect(departedLine?.employee_no).toBe('DEMO-E007')

    wrapper.unmount()
  })
})
