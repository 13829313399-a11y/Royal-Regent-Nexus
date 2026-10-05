import { flushPromises, mount } from '@vue/test-utils'
import { draftSource } from '@/lib/__tests__/fixtures/yinhuiDraftSource'
import { createYinhuiDraft, saveYinhuiDraft } from '@/lib/customerPriceConverters/yinhuiDraft'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import QuoteCenterPanel from '@/components/modules/sales/QuoteCenterPanel.vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import * as dickieConverter from '@/lib/customerPriceConverters/dicky'
import { combineDickieV2 } from '@/lib/customerPriceConverters/dickieV2'
import { createDickieMapping } from '@/lib/dickieQuote'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { customerPriceArtifactApi } from '@/api/customerPriceArtifact'
import { customerPricingSettingsApi } from '@/api/customerPricingSettings'
import * as buzzbeeConverter from '@/lib/customerPriceConverters/buzzbee'
import * as buzzbeeTemplate from '@/lib/customerPriceConverters/buzzbeeTemplate'
import { createXlsxWorkbook, parseXlsxWorkbook, type XlsxCellInput } from '@/lib/customerPriceConverters/xlsxLite'
import type { CustomerPricingSettings } from '@/lib/customerPriceConverters/pricingSettings'

vi.mock('@/api/customerPriceArtifact', () => ({
  customerPriceArtifactApi: {
    list: vi.fn(async () => []),
    consume: vi.fn(),
    download: vi.fn(),
  },
}))
vi.mock('@/api/customerPricingSettings', () => ({ customerPricingSettingsApi: {
  snapshot: vi.fn(async (factory_id: string, customer_id: string) => {
    const definitions = JSON.parse(readFileSync('shared/customerPriceDefaults.json', 'utf8'))[customer_id]
    return { factory_id, customer_id, revision: 0, snapshot_id: 'test-pricing', materials: definitions.materials, rates: Object.fromEntries(Object.entries(definitions.rates).map(([key, row]) => [key, (row as { value: number }).value])), texts: {}, updated_at: '', updated_by_name: '' }
  }), get: vi.fn(), save: vi.fn(),
} }))
vi.mock('@/api/quoteTranslation', () => ({ translateQuoteDescriptions: vi.fn(async () => { throw new Error('Test translation unavailable') }) }))

const customerPricePermissions = [
  'customer_price:read',
  'customer_price:settings_read',
  'customer_price:import_internal_quote',
  'customer_price:export_customer_quote',
  'customer_price:compare',
]

function mountPanel(
  username: string,
  deniedPermissions: string[] = [],
  factoryId = 'huaxing',
) {
  const effectiveAccess = customerPricePermissions.map((permissionCode) => ({
    permission_code: permissionCode,
    factory_id: factoryId,
    department: 'sales-business',
    effect: deniedPermissions.includes(permissionCode) ? 'deny' as const : 'allow' as const,
    allowed: !deniedPermissions.includes(permissionCode),
    source_type: deniedPermissions.includes(permissionCode) ? 'override' : 'role',
    source_ids: deniedPermissions.includes(permissionCode) ? ['override-1'] : ['sales_customer_owner'],
  }))

  useAuthStore().applySession({
    id: `user-${username}`,
    username,
    display_name: '普通业务',
    roles: ['车间业务跟客'],
    permissions: customerPricePermissions,
    grants: [{
      role_id: 'sales_customer_owner',
      role_code: 'sales_customer_owner',
      role_name: '车间业务跟客',
      factory_id: factoryId,
      department: 'sales-business',
      permissions: customerPricePermissions,
      data_scope: 'department',
    }],
    factory_scopes: [factoryId],
    department_scopes: ['sales-business'],
    authz_mode: 'enforce',
    effective_access: effectiveAccess,
    force_password_change: false,
  })

  useAppStore().setActiveFactory(factoryId as 'huaxing' | 'huakang-a' | 'huakang-b' | 'huakang-c' | 'huakang-d' | 'huadeng')
  return mount(QuoteCenterPanel)
}

function mountCrossFactoryPosition(scopeMode: 'cross_factory_read' | 'cross_factory_operate') {
  useAuthStore().applySession({
    id: 'user-cross-factory-sales',
    username: 'cross-factory-sales',
    display_name: '跨厂业务',
    roles: ['业务'],
    permissions: customerPricePermissions,
    grants: [{
      role_id: 'position_sales_business',
      role_code: 'position_sales_business',
      role_name: '业务',
      factory_id: 'huaxing',
      department: 'sales-business',
      permissions: customerPricePermissions,
      data_scope: 'all',
      scope_mode: scopeMode,
      read_permission_codes: ['customer_price:read'],
      unrestricted_department: true,
    }],
    factory_scopes: ['*', 'huaxing'],
    department_scopes: ['*', 'sales-business'],
    authz_mode: 'enforce',
    effective_access: customerPricePermissions.map((permissionCode) => ({
      permission_code: permissionCode,
      factory_id: 'huaxing',
      department: 'sales-business',
      effect: 'allow' as const,
      allowed: true,
      source_type: 'role_binding',
      source_ids: ['position-sales-binding'],
    })),
    force_password_change: false,
  })

  useAppStore().setActiveFactory('huadeng')
  return mount(QuoteCenterPanel)
}

describe('QuoteCenterPanel customer visibility', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    window.history.replaceState({}, '', '/')
  })
  afterEach(() => window.history.replaceState({}, '', '/'))

  it('keeps maintenance customer switching separate from an imported quote and applies its multiplier only once on repeated export', async () => {
    const definitions = JSON.parse(readFileSync('shared/customerPriceDefaults.json', 'utf8')).buzzbee
    const pricing: CustomerPricingSettings = {
      factory_id: 'huaxing', customer_id: 'buzzbee', revision: 1, snapshot_id: 'buzzbee-frozen',
      materials: definitions.materials,
      rates: { ...Object.fromEntries(Object.entries(definitions.rates).map(([key, row]) => [key, (row as { value: number }).value])), injection_multiplier: 1.2 },
      texts: {}, updated_at: '', updated_by_name: '',
    }
    vi.mocked(customerPricingSettingsApi.snapshot).mockClear().mockResolvedValueOnce(pricing)
    vi.mocked(customerPricingSettingsApi.get).mockImplementation(async (factory_id, customer_id) => ({
      ...pricing, factory_id, customer_id, rates: { injection_multiplier: 3 },
      rate_definitions: { injection_multiplier: { label: '注塑倍率', kind: 'multiplier' } },
    }))
    const rows: XlsxCellInput[][] = Array.from({ length: 15 }, () => [])
    rows[6] = ['倍率切换测试套装报价']
    rows[7] = ['', '', '名称', '料型', '料重(G)', '', '机型', '1出几套', '目标数', '啤工', '料金额']
    rows[8] = ['', '', '测试外壳', 'ABS料', 100, '', 18, 1, 2800, 2, 1.5]
    rows[9] = ['', '', '', '', 100]
    rows[11] = ['', '料价', '料价', 1.5]
    rows[12] = ['', '啤工', '啤工', 2]
    rows[13] = ['', '装配工', '装工', 1]
    const source = Uint8Array.from(createXlsxWorkbook([{ name: '明细', rows }])).buffer
    const file = new File([source], '倍率切换测试.xlsx')
    Object.defineProperty(file, 'arrayBuffer', { value: async () => source })
    const template = Uint8Array.from(readFileSync('public/templates/buzzbee-standard-template.bin')).buffer
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, arrayBuffer: async () => template })))
    Object.defineProperty(window.URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:pricing-test') })
    Object.defineProperty(window.URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    const download = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const convert = vi.spyOn(buzzbeeConverter, 'convertBuzzBeeInternalQuote')
    const exportWorkbook = vi.spyOn(buzzbeeTemplate, 'createBuzzBeeTemplateWorkbook')
    const wrapper = mountPanel('pricing-switch-sales')
    const output = () => wrapper.findAll('button').find(button => button.text() === '输出报客价 Excel')!
    try {
      const input = wrapper.get('[data-testid="quote-import-input"]')
      Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
      await input.trigger('change'); await flushPromises()
      expect(convert).toHaveBeenCalledTimes(1)
      const result = convert.mock.results[0]!.value as buzzbeeConverter.BuzzBeeConversionResult
      expect(result.sheets[0]!.quoteData.injectionBeer).toBe(2.4)
      await output().trigger('click'); await flushPromises()
      const selector = wrapper.get('[data-testid="pricing-settings-customer"]')
      expect(selector.findAll('option').map(option => option.text())).toEqual(['BuzzBee', '迪士尼', 'Dickie', '彩星', '银辉'])
      await wrapper.get('[data-testid="customer-pricing-settings"] button').trigger('click'); await flushPromises()
      for (const customer of ['yinhui', 'disney', 'dicky', 'caixing', 'buzzbee']) {
        await selector.setValue(customer); await flushPromises()
        expect(customerPricingSettingsApi.get).toHaveBeenLastCalledWith('huaxing', customer)
        expect(wrapper.get('[data-testid="customer-tab-buzzbee"]').attributes('aria-pressed')).toBe('true')
        expect(wrapper.text()).toContain('倍率切换测试.xlsx')
      }
      await wrapper.get('[data-testid="customer-tab-yinhui"]').trigger('click')
      expect(selector.element).toHaveProperty('value', 'buzzbee')
      await wrapper.get('[data-testid="customer-tab-buzzbee"]').trigger('click')
      await output().trigger('click'); await flushPromises()
      expect(convert).toHaveBeenCalledTimes(1)
      expect(customerPricingSettingsApi.snapshot).toHaveBeenCalledTimes(1)
      expect(customerPricingSettingsApi.save).not.toHaveBeenCalled()
      expect(exportWorkbook).toHaveBeenCalledTimes(2)
      for (const call of exportWorkbook.mock.results) {
        const workbook = parseXlsxWorkbook(Uint8Array.from(call.value as Uint8Array).buffer)
        expect(workbook.sheets[0]!.rows[6]![6]).toBe(2.4)
      }
      expect(wrapper.text()).not.toMatch(/李业务|啤机车间 A|Ben \/ Dickie|陈善杰|郑大能/)
      useAppStore().setActiveFactory('huakang-a'); await flushPromises()
      expect(wrapper.find('[data-testid="pricing-settings-customer"]').exists()).toBe(false)
      expect(wrapper.text()).not.toContain('倍率切换测试.xlsx')
    } finally {
      wrapper.unmount(); convert.mockRestore(); exportWorkbook.mockRestore(); download.mockRestore()
      vi.mocked(customerPricingSettingsApi.get).mockReset(); vi.unstubAllGlobals()
    }
  })

  it.skipIf(!process.env.DICKIE_V2_SAMPLE_DIR)('receives the actual released Dickie quote directly without an upload', async () => {
    const directory = process.env.DICKIE_V2_SAMPLE_DIR!
    const handoff = JSON.parse(readFileSync(join(directory, 'sample-handoff.json'), 'utf8'))
    const bytes = readFileSync(join(directory, 'Dickie-演示内部报价.xlsx'))
    const source = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)
    const blob = new Blob([source])
    Object.defineProperty(blob, 'arrayBuffer', { value: async () => source })
    vi.mocked(customerPriceArtifactApi.list).mockResolvedValueOnce([handoff])
    vi.mocked(customerPriceArtifactApi.download).mockResolvedValueOnce({ blob, sha256: handoff.sha256, releaseStage: 'p4_final_approved' })
    vi.mocked(customerPriceArtifactApi.consume).mockResolvedValueOnce({ ...handoff, status: 'consumed' })
    const upload = vi.spyOn(dickieConverter, 'convertDickyInternalQuote')
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    Object.defineProperty(window.URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:received-quote') })
    Object.defineProperty(window.URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    const wrapper = mountPanel('direct-receive-sales')
    try {
      await flushPromises()
      await wrapper.get(`[data-testid="consume-artifact-${handoff.id}"]`).trigger('click')
      await flushPromises()
      await vi.waitFor(() => expect(customerPriceArtifactApi.consume, wrapper.text().match(/接收或转换预检失败：[^。]+/)?.[0]).toHaveBeenCalledWith(handoff.id, `customer-price-ui:${handoff.id}`))
      await flushPromises()
      expect(upload).not.toHaveBeenCalled()
      expect(wrapper.get('[data-testid="dickie-direct-handoff"]').text()).toContain(`已接收内部报价：${handoff.quote_no}`)
      expect(wrapper.get('[data-testid="dickie-offer-preview"]').text()).toContain('8.5')
      const output = wrapper.findAll('button').find(button => button.text() === '输出报客价 Excel')!
      await output.trigger('click')
      await flushPromises()
      expect(wrapper.text()).toContain('Quotation')
      expect(click).toHaveBeenCalledTimes(2)
    } finally { wrapper.unmount(); upload.mockRestore(); click.mockRestore() }
  })

  it('lets an ordinary sales account see and switch every customer', async () => {
    const wrapper = mountPanel('ordinary-sales-user')
    const customerButtons = wrapper.findAll('button[aria-pressed]')

    expect(customerButtons.map((button) => button.text())).toEqual([
      'BuzzBee',
      '迪士尼',
      'Dickie',
      '彩星',
      '银辉',
    ])

    for (const [selectedIndex, customerButton] of customerButtons.entries()) {
      await customerButton.trigger('click')

      expect(customerButton.attributes('aria-pressed')).toBe('true')
      expect(wrapper.get('input[type="file"]').attributes('disabled')).toBeUndefined()
      customerButtons.forEach((otherButton, otherIndex) => {
        expect(otherButton.attributes('aria-pressed')).toBe(String(otherIndex === selectedIndex))
      })
    }
  })

  it('lets an ordinary sales account import for every customer without an account binding', () => {
    const wrapper = mountPanel('ordinary-sales-user')

    expect(wrapper.get('input[type="file"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).toContain('全部客户按相同权限操作')
  })

  it('still honors an explicit user-level import deny', () => {
    const wrapper = mountPanel('ordinary-sales-user', ['customer_price:import_internal_quote'])

    expect(wrapper.get('input[type="file"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('当前账号没有导入内部报价权限')
  })

  it('still honors an explicit user-level export deny', () => {
    const wrapper = mountPanel('ordinary-sales-user', ['customer_price:export_customer_quote'])

    expect(wrapper.get('input[type="file"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).toContain('仅可导入')
    expect(wrapper.text()).toContain('当前账号没有输出权限')
  })

  it('does not expose Huaxing customer mappings to a cross-factory operator', () => {
    const wrapper = mountCrossFactoryPosition('cross_factory_operate')

    expect(wrapper.findAll('button[aria-pressed]')).toHaveLength(0)
    expect(wrapper.get('input[type="file"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('当前厂区尚未配置报客映射')
  })

  it('keeps the selected non-Huaxing factory unmapped for cross-factory read positions', () => {
    const wrapper = mountCrossFactoryPosition('cross_factory_read')

    expect(wrapper.findAll('button[aria-pressed]')).toHaveLength(0)
    expect(wrapper.get('input[type="file"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('当前厂区尚未配置报客映射')
  })

  it('shows only the independently configured 360 mapping in Huakang A', () => {
    const wrapper = mountPanel('ordinary-sales-huakang-a', [], 'huakang-a')
    const customerButtons = wrapper.findAll('button[aria-pressed]')

    expect(customerButtons.map((button) => button.text())).toEqual(['360'])
    expect(wrapper.get('[data-testid="pricing-settings-customer"]').findAll('option').map(option => option.text())).toEqual(['360'])
    expect(wrapper.get('input[type="file"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).toContain('支持 .xlsx P4 / 原内部多 Sheet（无需 Breakdown）')
    expect(wrapper.text()).not.toMatch(/BuzzBee|迪士尼|Dickie|彩星/)
  })

  it('shows a complete visible error when a 360 import file is unsupported', async () => {
    const wrapper = mountPanel('ordinary-sales-huakang-a', [], 'huakang-a')
    const input = wrapper.get('[data-testid="quote-import-input"]')
    const file = new File(['legacy'], '360旧内部报价.xls', { type: 'application/vnd.ms-excel' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })

    await input.trigger('change')
    await flushPromises()

    expect(wrapper.get('[data-testid="quote-import-error"]').text()).toBe(
      '导入失败：360 当前支持 .xlsx P4 最终放行文件或原专用多 Sheet 工作簿，旧 .xls 请先另存为 .xlsx',
    )
  })
  it('opens a saved Silverlit draft, revokes confirmation immediately on replacement and clears it across factories', async () => {
    const wrapper = mountPanel('ordinary-sales-user')
    await wrapper.get('[data-testid="customer-tab-yinhui"]').trigger('click')
    const draft = createYinhuiDraft(draftSource(false), '银辉81209.xlsx')
    draft.result.quoteData.productName = 'Round Light'
    const saved = new TextEncoder().encode(saveYinhuiDraft(draft))
    const file = new File([saved], '银辉-内部核对草稿.json')
    Object.defineProperty(file, 'arrayBuffer', { value: async () => saved.buffer })
    const input = wrapper.get('[data-testid="quote-import-input"]')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await flushPromises()
    expect(wrapper.find('[data-testid="yinhui-draft"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="yinhui-confirm"]').element).toHaveProperty('checked', false)
    await wrapper.get('[data-testid="yinhui-confirm"]').setValue(true)
    expect(wrapper.get('[data-testid="yinhui-confirm"]').element).toHaveProperty('checked', true)
    let resolve!: (value: ArrayBuffer) => void
    const replacement = new File([], '银辉-替换.xlsx')
    Object.defineProperty(replacement, 'arrayBuffer', { value: () => new Promise<ArrayBuffer>(r => { resolve = r }) })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [replacement] })
    await input.trigger('change')
    expect(wrapper.get('[data-testid="yinhui-confirm"]').element).toHaveProperty('checked', false)
    expect(wrapper.get('[data-testid="yinhui-confirm"]').attributes('disabled')).toBeDefined()
    useAppStore().setActiveFactory('huadeng')
    await flushPromises()
    resolve(draftSource(false))
    await flushPromises()
    expect(wrapper.find('[data-testid="yinhui-draft"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('当前厂区尚未配置报客映射')
    wrapper.unmount()
  })
  it('recovers a Dickie batch after failed import and invalidates removed products before export', async () => {
    const wrapper = mountPanel('ordinary-sales-user')
    await wrapper.get('[data-testid="customer-tab-dicky"]').trigger('click')
    expect(wrapper.get('[data-testid="dickie-direct-handoff"]').text()).toContain('上方交接池接收并转换')
    const source = (id: string) => {
      const mapping = createDickieMapping()
      mapping.item_number = id; mapping.item_name = { zh: id, en: id }; mapping.quote_date = '2026-09-21'
      return combineDickieV2([{ sourceFileName: `${id}.xlsx`, sourceBuffer: new ArrayBuffer(0), summarySheetName: '总表', clientName: 'Dickie', quoteDate: new Date(), sheets: [], v2Data: { products: [{ identity: id, mapping, outerPack: 12, dimensions: '1 × 2 × 3', cartonDimensions: '10 × 20 × 30', cartonCbm: .006, offers: [{ label: { zh: '正常', en: 'Normal' }, remark: { zh: '', en: '' }, moq: '5000 pcs', prices: [10, 11, 12] }], molds: [] }] } }])
    }
    const spy = vi.spyOn(dickieConverter, 'convertDickyInternalQuote')
    const button = (name: string) => wrapper.findAll('button').find(b => b.text() === name)!
    const upload = async (name: string) => {
      const file = new File([], `${name}.xlsx`)
      Object.defineProperty(file, 'arrayBuffer', { value: async () => new ArrayBuffer(0) })
      const input = wrapper.get('[data-testid="quote-import-input"]')
      Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
      await input.trigger('change'); await flushPromises()
    }
    try {
      for (const id of ['DEMO-A', 'DEMO-B']) {
        spy.mockReturnValueOnce(source(id))
        await upload(id)
        await button('加入 Dickie 合并清单').trigger('click')
      }
      spy.mockImplementationOnce(() => { throw new Error('无效文件') })
      await upload('invalid')
      expect(button('预览合并报价').attributes('disabled')).toBeUndefined()
      await button('预览合并报价').trigger('click')
      expect(button('输出报客价 Excel')).toBeDefined()
      expect(wrapper.get('[data-testid="dickie-offer-preview"]').text()).toContain('20 柜 HKD')
      expect(wrapper.text()).not.toContain('内部价合计')
      await button('移除').trigger('click')
      expect(button('输出报客价 Excel')).toBeUndefined()
      await button('预览合并报价').trigger('click')
      expect(wrapper.text()).not.toContain('DEMO-A')
      expect(button('输出报客价 Excel')).toBeDefined()
      await button('清空清单').trigger('click')
      expect(button('输出报客价 Excel')).toBeUndefined()
      expect(wrapper.text()).not.toContain('DEMO-B')
    } finally { spy.mockRestore(); wrapper.unmount() }
  })

  it.each(['huakang-b', 'huakang-c', 'huakang-d', 'huadeng'] as const)(
    'starts %s with an independent unmapped conversion state and no Huaxing customer tabs',
    async (factoryId) => {
      const wrapper = mountPanel(`ordinary-sales-${factoryId}`, [], factoryId)
      const customerButtons = wrapper.findAll('button[aria-pressed]')

      expect(customerButtons).toHaveLength(0)
      expect(wrapper.get('input[type="file"]').attributes('disabled')).toBeDefined()
      expect(wrapper.text()).toContain('当前厂区尚未配置报客映射')
      expect(wrapper.text()).not.toMatch(/QTC-(?:HKA|HKB|HD)-|CQ-HD-/)
    },
  )
})
