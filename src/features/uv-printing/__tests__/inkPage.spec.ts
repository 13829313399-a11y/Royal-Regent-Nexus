import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type DOMWrapper } from '@vue/test-utils'
import { computed, ref, shallowRef } from 'vue'
import type {
  UvInkBalance,
  UvInkMovement,
  UvInkSku,
  UvPage,
  UvResponse,
  UvScope,
  UvWorkspaceTransport,
} from '../contracts'
import { UV_CONTEXT_KEY, UV_TRANSPORT_KEY, type UvPageContext } from '../composables/uvPageContext'
import { SAMPLE_BUSINESS_DATE, SAMPLE_FACTORY_ID } from '../preview/fixtures'
import { UvMemoryStore } from '../preview/memoryStore'
import InkPage from '../pages/InkPage.vue'
import { inkQuantityMl, normalizeInkDecimalInput } from '../components/InkIssueDrawer.vue'
import { describeInkScope, emptyInkFilters, filterInkStock, inkSurfaceState } from '../pages/InkPage.vue'

/**
 * 墨水账本页（spec 6.6）验收测试。
 *
 * 直接实例化 UvMemoryStore 作为 transport，通过 provide 注入 UV_TRANSPORT_KEY / UV_CONTEXT_KEY，
 * 不依赖 pinia：页面只从注入里取 transport 与 workspace。
 */

const routerQuery = vi.hoisted(() => ({ value: {} as Record<string, string> }))

vi.mock('vue-router', () => ({
  useRoute: () => ({
    name: 'uv-printing',
    path: '/modules/production/uv-printing/ink',
    query: routerQuery.value,
    params: {},
  }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

const FULL_PERMISSIONS = [
  'uv_printing:read',
  'uv_printing:report',
  'uv_printing:quality',
  'uv_printing:master_write',
  'uv_printing:shift_write',
  'uv_printing:ink_write',
  'uv_printing:cost_read',
  'uv_printing:cost_write',
  'uv_printing:payroll_read',
  'uv_printing:payroll_write',
  'uv_printing:export',
]

const ALL_SCOPE: UvScope = { factory_id: SAMPLE_FACTORY_ID, page_size: 200 }

/** 用于验证「空」状态的 transport：接口正常，但本厂区还没有任何墨水 SKU。 */
class EmptyInkStore extends UvMemoryStore {
  override async inkSkus(scope: UvScope): Promise<UvResponse<UvPage<UvInkSku>>> {
    void scope
    return {
      meta: { factory_id: SAMPLE_FACTORY_ID, as_of: '2026-09-13T06:20:00.000Z', data_mode: 'sample', coverage: 'no_data', warnings: [] },
      data: { items: [], total: 0, page: 1, page_size: 200 },
    }
  }

  override async inkBalances(scope: UvScope): Promise<UvResponse<UvPage<UvInkBalance>>> {
    void scope
    return {
      meta: { factory_id: SAMPLE_FACTORY_ID, as_of: '2026-09-13T06:20:00.000Z', data_mode: 'sample', coverage: 'no_data', warnings: [] },
      data: { items: [], total: 0, page: 1, page_size: 200 },
    }
  }
}

interface Harness {
  store: UvMemoryStore
  ctx: UvPageContext
  permissions: string[]
}

function createHarness(options: { store?: UvMemoryStore; permissions?: string[] } = {}): Harness {
  const store = options.store ?? new UvMemoryStore()
  const permissions = options.permissions ?? [...FULL_PERMISSIONS]
  const transport = shallowRef<UvWorkspaceTransport>(store)
  const revision = ref(0)
  const can = (permission: string) => permissions.includes(permission)
  const workspace = {
    can,
    permissionDenied: computed(() => !can('uv_printing:read')),
    isReadOnly: computed(() => !can('uv_printing:report')),
    isPreview: computed(() => true),
    scope: computed<UvScope>(() => ({ factory_id: SAMPLE_FACTORY_ID, business_date: SAMPLE_BUSINESS_DATE })),
    scopeFor: (overrides: Partial<UvScope> = {}) => ({
      factory_id: SAMPLE_FACTORY_ID,
      business_date: SAMPLE_BUSINESS_DATE,
      ...overrides,
    }),
    business_date: computed(() => SAMPLE_BUSINESS_DATE),
    shift: computed(() => 'all' as const),
    sampleAsOf: ref('2026-09-13T06:20:00.000Z'),
    workspacePath: '/modules/production/uv-printing',
  }
  const ctx = {
    workspace,
    transport,
    revision,
    markDirty: () => { revision.value += 1 },
    isPreview: ref(true),
  } as unknown as UvPageContext
  return { store, ctx, permissions }
}

function mountPage(harness: Harness) {
  return mount(InkPage, {
    global: {
      provide: {
        [UV_TRANSPORT_KEY]: harness.ctx.transport,
        [UV_CONTEXT_KEY]: harness.ctx,
      },
    },
  })
}

type Wrapper = ReturnType<typeof mountPage>

function buttonByText(wrapper: Wrapper, label: string): DOMWrapper<Element> {
  const found = wrapper.findAll('button').find((button) => button.text().trim() === label)
  if (!found) throw new Error(`没有找到按钮「${label}」，当前按钮：${wrapper.findAll('button').map((b) => b.text().trim()).join(' / ')}`)
  return found
}

function inputValue(wrapper: Wrapper, ariaLabel: string): string {
  const element = wrapper.get(`[aria-label="${ariaLabel}"]`).element as HTMLInputElement | HTMLSelectElement
  return element.value
}

function isChecked(wrapper: Wrapper, ariaLabel: string): boolean {
  return (wrapper.get(`[aria-label="${ariaLabel}"]`).element as HTMLInputElement).checked
}

async function movementsOf(store: UvMemoryStore): Promise<UvInkMovement[]> {
  const response = await store.inkMovements(ALL_SCOPE)
  return response.data.items
}

function balanceOf(store: UvMemoryStore, skuId: string): UvInkBalance | undefined {
  return store.inkBalancesSync().find((balance) => balance.sku_id === skuId)
}

/** 打开领用抽屉并选定 SKU / 数量 / 经手人。 */
async function fillIssueForm(
  wrapper: Wrapper,
  input: { skuId: string; unit?: 'bottle' | 'ml'; amount: string; handler?: string },
) {
  await buttonByText(wrapper, '领用出库').trigger('click')
  await flushPromises()
  await wrapper.get('select[aria-label="墨水 SKU"]').setValue(input.skuId)
  await flushPromises()
  if (input.unit) {
    await wrapper.get('select[aria-label="出库单位"]').setValue(input.unit)
    await flushPromises()
  }
  await wrapper.get('input[aria-label="出库数量"]').setValue(input.amount)
  await wrapper.get('input[aria-label="经手人"]').setValue(input.handler ?? 'DEMO 仓管甲')
  await flushPromises()
}

describe('墨水账本 · 纯函数口径', () => {
  it('500ml 包装按瓶换算成 ml 时不会乘 1000', () => {
    expect(inkQuantityMl('2', 'bottle', '500')).toBe('1000')
    expect(inkQuantityMl('2', 'bottle', '1000')).toBe('2000')
    expect(inkQuantityMl('750.5', 'ml', '500')).toBe('750.5')
    expect(inkQuantityMl('2', 'bottle', null)).toBe('0')
    expect(normalizeInkDecimalInput('abc')).toBe('')
    expect(normalizeInkDecimalInput(' 12.5 ')).toBe('12.5')
  })

  it('加载/空/无结果/无权限/失败/过期六种状态互相可区分', () => {
    const base = { forbidden: false, loading: false, settled: true, hasData: true, failed: false, sourceCount: 3, filteredCount: 3 }
    expect(inkSurfaceState({ ...base, forbidden: true })).toBe('forbidden')
    expect(inkSurfaceState({ ...base, loading: true, hasData: false, settled: false })).toBe('loading')
    expect(inkSurfaceState({ ...base, failed: true, hasData: false, settled: true })).toBe('error')
    expect(inkSurfaceState({ ...base, failed: true })).toBe('stale')
    expect(inkSurfaceState({ ...base, sourceCount: 0, filteredCount: 0 })).toBe('empty')
    expect(inkSurfaceState({ ...base, filteredCount: 0 })).toBe('no-result')
    expect(inkSurfaceState(base)).toBe('ready')
  })

  it('导出文案包含当前全部过滤条件', () => {
    const filters = { ...emptyInkFilters(), supplier: 'DEMO 供应商 B', material: 'hard' as const, lowOnly: true, q: '白' }
    const label = describeInkScope({
      view: 'flows',
      businessDate: SAMPLE_BUSINESS_DATE,
      shift: 'all',
      filters,
      totalCount: 14,
      resultCount: 2,
    })
    expect(label).toContain('墨水流水')
    expect(label).toContain(`业务日 ${SAMPLE_BUSINESS_DATE}`)
    expect(label).toContain('供应商 DEMO 供应商 B')
    expect(label).toContain('材质 硬墨')
    expect(label).toContain('关键字 白')
    expect(label).toContain('仅看低于阈值')
    expect(label).toContain('结果 2/14 条')
  })

  it('库存筛选按 SKU 独立判断，同色不同供应商不会被合并', () => {
    const skuA = { id: 'A', supplier: 'A厂', material: 'hard' as const, color: '白', color_aliases: [], package_ml: '1000', location: '', threshold_ml: '800', unit_cost: null, currency: null, is_active: true, factory_id: SAMPLE_FACTORY_ID, version: 1, created_at: '', updated_at: '' }
    const skuB = { ...skuA, id: 'B', supplier: 'B厂' }
    const balance = { sku_id: 'A', available_ml: '100', package_ml: '1000', bottle_equivalent: '0.1', threshold_ml: '800', low_stock: true, cost_pending: false }
    const rows = [
      { sku: skuA, balance },
      { sku: skuB, balance: { ...balance, sku_id: 'B', available_ml: '900', low_stock: false } },
    ]
    expect(filterInkStock(rows, emptyInkFilters())).toHaveLength(2)
    expect(filterInkStock(rows, { ...emptyInkFilters(), supplier: 'A厂' }).map((row) => row.sku.id)).toEqual(['A'])
    expect(filterInkStock(rows, { ...emptyInkFilters(), material: 'hard' })).toHaveLength(2)
    expect(filterInkStock(rows, { ...emptyInkFilters(), color: '白' })).toHaveLength(2)
    expect(filterInkStock(rows, { ...emptyInkFilters(), lowOnly: true }).map((row) => row.sku.id)).toEqual(['A'])
    expect(filterInkStock(rows, { ...emptyInkFilters(), q: 'B厂' }).map((row) => row.sku.id)).toEqual(['B'])
  })
})

describe('墨水账本页 · 库存与流水', () => {
  it('500ml 包装领 2 瓶产生 1000ml 出库，不是 2000ml', async () => {
    const harness = createHarness()
    const { store } = harness
    // DEMO-SKU-03 是 500ml 包装（供应商 A · 软墨 · 白），样例当日已领完，先补一笔入库恢复库存。
    await store.createInkPurchase({
      factory_id: SAMPLE_FACTORY_ID,
      operation_id: 'test-purchase-sku-03',
      sku_id: 'DEMO-SKU-03',
      quantity_ml: '1000',
      bottle_input: '2',
      occurred_on: SAMPLE_BUSINESS_DATE,
      machine_id: null,
      purpose: '采购入库',
      source_doc: 'TEST-PO-1',
      created_by_name: 'DEMO 仓管甲',
      unit_cost: null,
      currency: null,
    })
    expect(balanceOf(store, 'DEMO-SKU-03')?.available_ml).toBe('1000')

    const before = new Set((await movementsOf(store)).map((movement) => movement.id))
    const wrapper = mountPage(harness)
    await flushPromises()

    await fillIssueForm(wrapper, { skuId: 'DEMO-SKU-03', amount: '2' })

    // 抽屉里必须先显示库存、包装容量与实时换算结果。
    expect(wrapper.text()).toContain('当前可用库存')
    expect(wrapper.text()).toContain('1000 ml')
    expect(wrapper.text()).toContain('500 ml/瓶')
    expect(wrapper.text()).toContain('2 瓶 × 500 ml/瓶 = 1000 ml')
    expect(wrapper.text()).not.toContain('= 2000 ml')
    expect(wrapper.text()).toContain('例：500ml 包装领 2 瓶 = 1000ml')

    await buttonByText(wrapper, '确认出库').trigger('click')
    await flushPromises()

    const created = (await movementsOf(store)).find((movement) => !before.has(movement.id))
    expect(created).toBeDefined()
    expect(created?.kind).toBe('issue_out')
    expect(created?.sku_id).toBe('DEMO-SKU-03')
    expect(created?.quantity_ml).toBe('1000')
    expect(created?.signed_ml).toBe('-1000')
    expect(created?.bottle_input).toBe('2')
    expect(balanceOf(store, 'DEMO-SKU-03')?.available_ml).toBe('0')
  })

  it('同色不同供应商不能被互相抵扣', async () => {
    const harness = createHarness()
    const { store } = harness
    // DEMO-SKU-01 与 DEMO-SKU-02 都是「硬墨 · 白」，但供应商不同，余额各自独立。
    expect(balanceOf(store, 'DEMO-SKU-01')?.available_ml).toBe('800')
    expect(balanceOf(store, 'DEMO-SKU-02')?.available_ml).toBe('500')

    // 供应商 B 只有 500ml：领 600ml 必须被拒绝，且不能动用供应商 A 的 800ml。
    await expect(store.createInkIssue({
      factory_id: SAMPLE_FACTORY_ID,
      operation_id: 'test-issue-cross-supplier',
      sku_id: 'DEMO-SKU-02',
      quantity_ml: '600',
      bottle_input: null,
      occurred_on: SAMPLE_BUSINESS_DATE,
      machine_id: null,
      purpose: '生产领用',
      source_doc: '',
      created_by_name: 'DEMO 仓管乙',
    })).rejects.toMatchObject({ code: 'uv_insufficient_stock', status: 422 })

    expect(balanceOf(store, 'DEMO-SKU-02')?.available_ml).toBe('500')
    expect(balanceOf(store, 'DEMO-SKU-01')?.available_ml).toBe('800')

    // 页面上两行各自展示自己的可用量与阈值，不合并、不互相补足。
    const wrapper = mountPage(harness)
    await flushPromises()
    await wrapper.get('select[aria-label="供应商"]').setValue('DEMO 供应商 A')
    await flushPromises()
    const rows = wrapper.findAll('tr[data-sku-id]')
    expect(rows.map((row) => row.attributes('data-sku-id'))).toEqual(['DEMO-SKU-01', 'DEMO-SKU-03', 'DEMO-SKU-04'])
    expect(wrapper.find('tr[data-sku-id="DEMO-SKU-02"]').exists()).toBe(false)
    // 供应商 A 的白色硬墨仍是 800ml，没有被 B 的缺口扣掉。
    expect(wrapper.get('tr[data-sku-id="DEMO-SKU-01"]').text()).toContain('800')
    expect(wrapper.get('tr[data-sku-id="DEMO-SKU-01"]').text()).toContain('阈值')
  })

  it('缺单价的 SKU 出库成功，但金额显示待核而不是 0', async () => {
    const harness = createHarness()
    const { store } = harness
    expect(balanceOf(store, 'DEMO-SKU-05')?.available_ml).toBe('600')

    const before = new Set((await movementsOf(store)).map((movement) => movement.id))
    const wrapper = mountPage(harness)
    await flushPromises()

    await fillIssueForm(wrapper, { skuId: 'DEMO-SKU-05', unit: 'ml', amount: '100', handler: 'DEMO 仓管乙' })
    expect(wrapper.text()).toContain('该 SKU 没有单价：数量照常出库，金额会显示「待核」，不会显示成 0。')
    await buttonByText(wrapper, '确认出库').trigger('click')
    await flushPromises()

    const created = (await movementsOf(store)).find((movement) => !before.has(movement.id))
    expect(created?.quantity_ml).toBe('100')
    expect(created?.cost_pending).toBe(true)
    expect(created?.unit_cost).toBeNull()
    expect(created?.amount).toBeNull()
    expect(balanceOf(store, 'DEMO-SKU-05')?.available_ml).toBe('500')

    // 流水表里这条记录的成本列是「待核」，不是 0。
    await wrapper.get('input[aria-label="按关键字搜索墨水"]').setValue('品红')
    await flushPromises()
    await buttonByText(wrapper, '流水').trigger('click')
    await flushPromises()
    const row = wrapper.get(`tr[data-movement-id="${created?.id}"]`)
    expect(row.text()).toContain('待核')
    expect(row.text()).not.toContain('HK$0.00')
    expect(wrapper.text()).toContain('成本待核')
  })

  it('冲销保留原流水并生成关联的反向记录', async () => {
    const harness = createHarness()
    const { store } = harness
    const originalId = 'DEMO-IM-5008'
    const before = await movementsOf(store)
    expect(before.some((movement) => movement.id === originalId)).toBe(true)
    expect(balanceOf(store, 'DEMO-SKU-01')?.available_ml).toBe('800')

    const wrapper = mountPage(harness)
    await flushPromises()
    await buttonByText(wrapper, '流水').trigger('click')
    await flushPromises()

    const originalRow = wrapper.get(`tr[data-movement-id="${originalId}"]`)
    const reverseButton = originalRow.findAll('button').find((button) => button.text().trim() === '冲销')
    expect(reverseButton).toBeDefined()
    await reverseButton!.trigger('click')
    await flushPromises()

    // 冲销必须先确认影响并填写原因，空原因不能提交。
    expect(wrapper.text()).toContain('冲销这条墨水流水？')
    expect(wrapper.text()).toContain(originalId)
    const confirm = buttonByText(wrapper, '确认冲销')
    expect(confirm.attributes('disabled')).toBeDefined()
    await wrapper.get('textarea').setValue('领用登记错误，货没出库')
    await flushPromises()
    await confirm.trigger('click')
    await flushPromises()

    const after = await movementsOf(store)
    expect(after).toHaveLength(before.length + 1)
    const reversal = after.find((movement) => movement.kind === 'reversal')
    expect(reversal).toBeDefined()
    expect(reversal?.reverses_movement_id).toBe(originalId)
    expect(reversal?.signed_ml).toBe('2200')
    // 原流水没有消失，并指向冲销记录。
    const original = after.find((movement) => movement.id === originalId)
    expect(original).toBeDefined()
    expect(original?.reversed_by_id).toBe(reversal?.id)
    expect(balanceOf(store, 'DEMO-SKU-01')?.available_ml).toBe('3000')

    // 界面上原流水仍在列表里，标记已冲销且不再提供「冲销」按钮；冲销行带原单链接。
    const originalAfter = wrapper.get(`tr[data-movement-id="${originalId}"]`)
    expect(originalAfter.text()).toContain('已冲销')
    expect(originalAfter.findAll('button').some((button) => button.text().trim() === '冲销')).toBe(false)
    const reversalRow = wrapper.get(`tr[data-movement-id="${reversal?.id}"]`)
    expect(reversalRow.text()).toContain('原单')
    expect(reversalRow.text()).toContain(originalId)
  })

  it('库存不足时返回结构化错误、余额不为负、表单保留并可重试', async () => {
    const harness = createHarness()
    const { store } = harness
    const before = await movementsOf(store)
    const wrapper = mountPage(harness)
    await flushPromises()

    await fillIssueForm(wrapper, { skuId: 'DEMO-SKU-01', unit: 'ml', amount: '900' })
    await buttonByText(wrapper, '确认出库').trigger('click')
    await flushPromises()

    // 字段级错误带可用量，表单内容保留，重试入口仍在。
    expect(wrapper.get('#ink-issue-quantity-error').text()).toContain('库存不足')
    expect(wrapper.get('#ink-issue-quantity-error').text()).toContain('800')
    expect(inputValue(wrapper, '出库数量')).toBe('900')
    expect(inputValue(wrapper, '墨水 SKU')).toBe('DEMO-SKU-01')
    expect(buttonByText(wrapper, '重试提交').attributes('disabled')).toBeUndefined()
    // 阻断信息用 role="alert"，不只靠会自动消失的 Toast。
    expect(wrapper.findAll('[role="alert"]').length).toBeGreaterThan(0)

    // 没有新的流水，余额不为负，也没有回落到任何样例数字。
    expect(await movementsOf(store)).toHaveLength(before.length)
    expect(balanceOf(store, 'DEMO-SKU-01')?.available_ml).toBe('800')
    expect(store.inkBalancesSync().every((balance) => !balance.available_ml.startsWith('-'))).toBe(true)
  })

  it('切换库存 / 流水视图保留搜索与筛选条件', async () => {
    const harness = createHarness()
    const wrapper = mountPage(harness)
    await flushPromises()

    const expected = {
      q: '白',
      supplier: 'DEMO 供应商 A',
      material: 'hard',
      color: '白',
      lowOnly: true,
    }
    await wrapper.get('input[aria-label="按关键字搜索墨水"]').setValue(expected.q)
    await wrapper.get('select[aria-label="供应商"]').setValue(expected.supplier)
    await wrapper.get('select[aria-label="墨水材质"]').setValue(expected.material)
    await wrapper.get('select[aria-label="颜色"]').setValue(expected.color)
    await flushPromises()

    // 组合条件生效：供应商 A + 硬墨 + 白色只剩 DEMO-SKU-01。
    expect(wrapper.findAll('tr[data-sku-id]').map((row) => row.attributes('data-sku-id'))).toEqual(['DEMO-SKU-01'])

    await wrapper.get('input[aria-label="仅看低库"]').setValue(true)
    await flushPromises()
    // SKU-01 是 800ml / 阈值 800ml，不算低库，于是变成「无结果」而不是空白或 0。
    expect(wrapper.findAll('tr[data-sku-id]')).toHaveLength(0)
    expect(wrapper.text()).toContain('没有符合条件的墨水库存')

    await buttonByText(wrapper, '流水').trigger('click')
    await flushPromises()

    // 条件全部保留；流水视图同样按 SKU 的供应商 / 材质 / 颜色过滤。
    expect(inputValue(wrapper, '按关键字搜索墨水')).toBe(expected.q)
    expect(inputValue(wrapper, '供应商')).toBe(expected.supplier)
    expect(inputValue(wrapper, '墨水材质')).toBe(expected.material)
    expect(inputValue(wrapper, '颜色')).toBe(expected.color)
    expect(isChecked(wrapper, '仅看低库')).toBe(true)
    expect(wrapper.text()).toContain('库存视图条件，已保留，切回库存仍然生效')
    expect(wrapper.find('tr[data-movement-id="DEMO-IM-5008"]').exists()).toBe(true)
    expect(wrapper.find('tr[data-movement-id="DEMO-IM-5009"]').exists()).toBe(false)

    await buttonByText(wrapper, '库存').trigger('click')
    await flushPromises()
    expect(inputValue(wrapper, '按关键字搜索墨水')).toBe(expected.q)
    expect(inputValue(wrapper, '供应商')).toBe(expected.supplier)
    expect(inputValue(wrapper, '墨水材质')).toBe(expected.material)
    expect(inputValue(wrapper, '颜色')).toBe(expected.color)
    expect(isChecked(wrapper, '仅看低库')).toBe(true)
    expect(wrapper.findAll('tr[data-sku-id]')).toHaveLength(0)
  })

  it('按 URL 条件打开时直接落在库存 + 仅看低库，且只有真正低于阈值的 SKU', async () => {
    routerQuery.value = { view: 'stock', low: '1' }
    try {
      const harness = createHarness()
      const wrapper = mountPage(harness)
      await flushPromises()
      expect(isChecked(wrapper, '仅看低库')).toBe(true)
      // 样例里只有 DEMO-SKU-03（软墨白，0ml / 阈值 400ml）低于阈值。
      expect(wrapper.findAll('tr[data-sku-id]').map((row) => row.attributes('data-sku-id'))).toEqual(['DEMO-SKU-03'])
      expect(wrapper.get('tr[data-sku-id="DEMO-SKU-03"]').text()).toContain('低于预警阈值')
      expect(wrapper.get('tr[data-sku-id="DEMO-SKU-03"]').text()).toContain('低于阈值 400 ml，需要补货')
    } finally {
      routerQuery.value = {}
    }
  })
})

describe('墨水账本页 · 权限与导出', () => {
  it('没有 ink_write 时写按钮禁用、给出原因，并说明服务端才是权威校验', async () => {
    const harness = createHarness({ permissions: ['uv_printing:read', 'uv_printing:cost_read'] })
    const wrapper = mountPage(harness)
    await flushPromises()

    expect(buttonByText(wrapper, '领用出库').attributes('disabled')).toBeDefined()
    expect(buttonByText(wrapper, '采购入库').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('缺少 uv_printing:ink_write')
    expect(wrapper.text()).toContain('服务端才是权威校验')

    // 冲销动作在流水视图里同样禁用。
    await buttonByText(wrapper, '流水').trigger('click')
    await flushPromises()
    const reverseButton = wrapper
      .get('tr[data-movement-id="DEMO-IM-5008"]')
      .findAll('button')
      .find((button) => button.text().trim() === '冲销')
    expect(reverseButton).toBeDefined()
    expect(reverseButton?.attributes('disabled')).toBeDefined()
    expect(reverseButton?.attributes('aria-label')).toContain('uv_printing:ink_write')
  })

  it('没有 cost_read 时单价与金额列显示未授权，且不渲染任何金额数字', async () => {
    const harness = createHarness({ permissions: ['uv_printing:read', 'uv_printing:ink_write'] })
    const wrapper = mountPage(harness)
    await flushPromises()
    await buttonByText(wrapper, '流水').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('未授权')
    expect(wrapper.text()).toContain('uv_printing:cost_read')
    // 样例里的 295.00 / 0.2950 等成本数字一个都不能出现。
    expect(wrapper.text()).not.toContain('HK$')
    expect(wrapper.text()).not.toContain('0.295')
    expect(wrapper.text()).not.toContain('0.32')
  })

  it('导出按钮受 uv_printing:export 控制，点击后给出与页面一致的过滤条件', async () => {
    const denied = createHarness({ permissions: ['uv_printing:read', 'uv_printing:ink_write', 'uv_printing:cost_read'] })
    const deniedWrapper = mountPage(denied)
    await flushPromises()
    expect(buttonByText(deniedWrapper, '样例导出').attributes('disabled')).toBeDefined()

    const allowed = createHarness()
    const wrapper = mountPage(allowed)
    await flushPromises()
    await wrapper.get('select[aria-label="供应商"]').setValue('DEMO 供应商 B')
    await flushPromises()
    await buttonByText(wrapper, '样例导出').trigger('click')
    await flushPromises()

    const toast = wrapper.get('.uv-toast')
    expect(toast.text()).toContain('样例导出（不生成文件）')
    expect(toast.text()).toContain('导出与网页使用同一过滤条件')
    expect(toast.text()).toContain('供应商 DEMO 供应商 B')
    expect(toast.text()).toContain(`业务日 ${SAMPLE_BUSINESS_DATE}`)
  })

  it('没有 read 权限时显示无权限状态，而不是空数据或样例数据', async () => {
    const harness = createHarness({ permissions: [] })
    const wrapper = mountPage(harness)
    await flushPromises()
    expect(wrapper.text()).toContain('没有查看墨水库存的权限')
    expect(wrapper.findAll('tr[data-sku-id]')).toHaveLength(0)
  })

  it('真正没有 SKU 主数据时是「空」，有数据但被筛掉时是「无结果」', async () => {
    // 空：接口正常返回 0 个 SKU / 0 条余额，不是失败。
    const harness = createHarness({ store: new EmptyInkStore() })
    const wrapper = mountPage(harness)
    await flushPromises()
    expect(wrapper.text()).toContain('当前范围还没有墨水库存')
    expect(wrapper.text()).not.toContain('读取墨水库存失败')

    // 无结果：有数据，但筛选条件筛掉了全部行。
    const full = createHarness()
    const other = mountPage(full)
    await flushPromises()
    await other.get('input[aria-label="按关键字搜索墨水"]').setValue('不存在的颜色')
    await flushPromises()
    expect(other.text()).toContain('没有符合条件的墨水库存')
    expect(other.text()).toContain('清除筛选')
  })

  it('刷新失败但已有旧数据时标记为「已过期」，不假装数字仍然有效', async () => {
    const harness = createHarness()
    const wrapper = mountPage(harness)
    await flushPromises()
    expect(wrapper.findAll('tr[data-sku-id]').length).toBeGreaterThan(0)

    harness.store.failure.readFailure = true
    harness.ctx.markDirty()
    await flushPromises()

    expect(wrapper.text()).toContain('墨水库存已过期')
    expect(wrapper.findAll('tr[data-sku-id]')).toHaveLength(0)
  })

  it('读取失败时显示失败状态与重试，不回落到样例数据也不显示 0', async () => {
    const harness = createHarness()
    harness.store.failure.readFailure = true
    const wrapper = mountPage(harness)
    await flushPromises()

    expect(wrapper.text()).toContain('读取墨水库存失败')
    expect(wrapper.text()).toContain('重试读取')
    expect(wrapper.findAll('tr[data-sku-id]')).toHaveLength(0)

    harness.store.failure.readFailure = false
    await buttonByText(wrapper, '重试读取').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('tr[data-sku-id]').length).toBeGreaterThan(0)
  })

  it('其他页面的写操作会通过 revision 让本页重新读取', async () => {
    const harness = createHarness()
    const wrapper = mountPage(harness)
    await flushPromises()
    expect(wrapper.get('tr[data-sku-id="DEMO-SKU-06"]').text()).toContain('420')

    await harness.store.createInkPurchase({
      factory_id: SAMPLE_FACTORY_ID,
      operation_id: 'test-purchase-sku-06',
      sku_id: 'DEMO-SKU-06',
      quantity_ml: '500',
      bottle_input: '0.5',
      occurred_on: SAMPLE_BUSINESS_DATE,
      machine_id: null,
      purpose: '采购入库',
      source_doc: 'TEST-PO-2',
      created_by_name: 'DEMO 仓管甲',
      unit_cost: '0.210000',
      currency: 'HKD',
    })
    harness.ctx.markDirty()
    await flushPromises()

    expect(wrapper.get('tr[data-sku-id="DEMO-SKU-06"]').text()).toContain('920')
  })

  it('流水列覆盖发生日 / 类型 / SKU / 有符号数量 / 折合瓶 / 机台用途 / 单号 / 创建人', async () => {
    const harness = createHarness()
    const wrapper = mountPage(harness)
    await flushPromises()
    await buttonByText(wrapper, '流水').trigger('click')
    await flushPromises()

    const headers = wrapper.findAll('thead th').map((th) => th.text())
    expect(headers).toEqual([
      '发生日',
      '类型',
      'SKU（供应商 · 材质 · 颜色）',
      '数量 ml（有符号）',
      '折合瓶',
      '单价',
      '金额',
      '机台 · 用途',
      '来源单号',
      '创建人',
      '操作',
    ])

    const row = wrapper.get('tr[data-movement-id="DEMO-IM-5008"]')
    expect(row.text()).toContain('2026-09-13')
    expect(row.text()).toContain('领用出库')
    expect(row.text()).toContain('-2200')
    expect(row.text()).toContain('DEMO 仓管甲')
    expect(row.text()).toContain('UV-01')
  })
})
