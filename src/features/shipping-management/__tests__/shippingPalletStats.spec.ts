import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ShippingPalletStatsPanel from '../ShippingPalletStatsPanel.vue'

const fetchShippingPalletStatsMock = vi.hoisted(() => vi.fn())
const exportShippingPalletStatsMock = vi.hoisted(() => vi.fn())
const createShippingPalletRecordMock = vi.hoisted(() => vi.fn())
const updateShippingPalletRecordMock = vi.hoisted(() => vi.fn())
const updateShippingPalletGroupMock = vi.hoisted(() => vi.fn())
const batchDeleteShippingPalletRecordsMock = vi.hoisted(() => vi.fn())
const restoreExcludedShippingPalletRecordsMock = vi.hoisted(() => vi.fn())

vi.mock('@/api/shippingMail', () => ({
  fetchShippingPalletStats: fetchShippingPalletStatsMock,
  exportShippingPalletStats: exportShippingPalletStatsMock,
  createShippingPalletRecord: createShippingPalletRecordMock,
  updateShippingPalletRecord: updateShippingPalletRecordMock,
  updateShippingPalletGroup: updateShippingPalletGroupMock,
  batchDeleteShippingPalletRecords: batchDeleteShippingPalletRecordsMock,
  restoreExcludedShippingPalletRecords: restoreExcludedShippingPalletRecordsMock,
}))

const SAMPLE_RESPONSE = {
  year: '2026',
  month: '2026-11',
  factoryId: 'huaxing',
  customer: 'all',
  q: '',
  availableFactories: [
    { id: 'huaxing', name: '华兴' },
    { id: 'huadeng', name: '华登' },
  ],
  availableCustomers: ['ROSS', 'SIMBA'],
  availableYears: ['2026', '2025'],
  availableMonths: ['2026-11', '2026-10'],
  excludedCount: 0,
  summary: {
    totalPallets: 15,
    totalContainers: 2,
    estimatedCost: 1075,
    recordCount: 2,
    customerCount: 2,
  },
  groups: [
    {
      key: 'huaxing||ROSS||出口熏蒸卡板 (1100×1100)',
      factoryId: 'huaxing',
      factoryName: '华兴',
      customer: 'ROSS',
      spec: '出口熏蒸卡板 (1100×1100)',
      unitPrice: 75,
      containerCount: 1,
      totalPallets: 10,
      estimatedCost: 750,
      recordCount: 1,
    },
    {
      key: 'huaxing||SIMBA||标准木卡板 (1200×1000)',
      factoryId: 'huaxing',
      factoryName: '华兴',
      customer: 'SIMBA',
      spec: '标准木卡板 (1200×1000)',
      unitPrice: 65,
      containerCount: 1,
      totalPallets: 5,
      estimatedCost: 325,
      recordCount: 1,
    },
  ],
  details: [
    {
      id: 'load-1',
      factoryId: 'huaxing',
      factoryName: '华兴',
      date: '2026-11-23',
      customer: 'ROSS',
      containerNo: 'MSKU1234567',
      containerType: '40GP',
      soNo: '279188253',
      contractNo: '298379137',
      filingCodes: ['ROSS-279188253'],
      spec: '出口熏蒸卡板 (1100×1100)',
      cartons: 100,
      pallets: 10,
      unitPrice: 75,
      estimatedCost: 750,
      source: '柜货单',
      isContainer: true,
      recordType: 'loading_sheet' as const,
      editable: false,
      remark: '',
    },
    {
      id: 'load-2',
      factoryId: 'huaxing',
      factoryName: '华兴',
      date: '2026-11-24',
      customer: 'SIMBA',
      containerNo: 'HMMU8888888',
      containerType: '40HQ',
      soNo: 'HKGGC6501802',
      contractNo: 'HAMN00411A',
      filingCodes: ['TRICYCLE-6501802'],
      spec: '标准木卡板 (1200×1000)',
      cartons: 50,
      pallets: 5,
      unitPrice: 65,
      estimatedCost: 325,
      source: '柜货单 / 补料单',
      isContainer: true,
      recordType: 'loading_sheet' as const,
      editable: false,
      remark: '',
    },
  ],
}

describe('ShippingPalletStatsPanel', () => {
  const mountedWrappers: Array<ReturnType<typeof mount>> = []

  function mountPanel() {
    const wrapper = mount(ShippingPalletStatsPanel, {
      props: { factoryId: 'huaxing' },
      attachTo: document.body,
    })
    mountedWrappers.push(wrapper)
    return wrapper
  }

  beforeEach(() => {
    fetchShippingPalletStatsMock.mockReset()
    exportShippingPalletStatsMock.mockReset()
    createShippingPalletRecordMock.mockReset()
    updateShippingPalletRecordMock.mockReset()
    updateShippingPalletGroupMock.mockReset()
    batchDeleteShippingPalletRecordsMock.mockReset()
    restoreExcludedShippingPalletRecordsMock.mockReset()

    fetchShippingPalletStatsMock.mockResolvedValue(SAMPLE_RESPONSE)
    exportShippingPalletStatsMock.mockResolvedValue(new Blob(['xlsx-bytes']))
    createShippingPalletRecordMock.mockResolvedValue({ id: 'pallet-new' })
    updateShippingPalletRecordMock.mockResolvedValue({ id: 'pallet-new' })
    updateShippingPalletGroupMock.mockResolvedValue({ updatedCount: 1 })
    batchDeleteShippingPalletRecordsMock.mockResolvedValue({
      deletedManualCount: 0,
      excludedSyncCount: 1,
      totalRemoved: 1,
    })
    restoreExcludedShippingPalletRecordsMock.mockResolvedValue({ restoredCount: 1 })
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn().mockReturnValue('blob:mock-pallet'),
      revokeObjectURL: vi.fn(),
    })
  })

  afterEach(() => {
    while (mountedWrappers.length) {
      mountedWrappers.pop()?.unmount()
    }
    document.body.innerHTML = ''
  })

  it('renders 年/月, 厂区, 客户 selectors, search box, 添加卡板, 删除选中, 3 KPI cards, and default summary view', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.find('[aria-label="年份"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="月份"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="厂区"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="客户"]').exists()).toBe(true)
    expect(wrapper.find('input[aria-label="搜索卡板记录"]').exists()).toBe(true)
    expect(wrapper.findAll('button').some((b) => b.text().includes('添加卡板'))).toBe(true)
    expect(wrapper.findAll('button').some((b) => b.text().includes('删除选中'))).toBe(true)

    const text = wrapper.text()
    expect(text).toContain('当月总用板数')
    expect(text).toContain('15')
    expect(text).toContain('总柜数')
    expect(text).toContain('2')
    expect(text).toContain('预估卡板总费用')
    expect(text).toContain('1,075.00')

    expect(text).toContain('按客户 / 规格汇总（2）')
    expect(text).toContain('出口熏蒸卡板 (1100×1100)')
    expect(text).not.toContain('MSKU1234567')
  })

  it('supports adding manual pallet records and keyword searching', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    const addBtn = wrapper.findAll('button').find((b) => b.text().includes('添加卡板'))!
    await addBtn.trigger('click')
    await flushPromises()

    const dateInput = document.body.querySelector<HTMLInputElement>('#manual-ship-date')!
    const customerInput = document.body.querySelector<HTMLInputElement>('#manual-customer')!
    const palletsInput = document.body.querySelector<HTMLInputElement>('#manual-pallets')!
    const remarkInput = document.body.querySelector<HTMLInputElement>('#manual-remark')!
    expect(dateInput).toBeTruthy()

    dateInput.value = '2025-08-12'
    dateInput.dispatchEvent(new Event('input'))
    customerInput.value = 'ZURU'
    customerInput.dispatchEvent(new Event('input'))
    palletsInput.value = '12'
    palletsInput.dispatchEvent(new Event('input'))
    remarkInput.value = '年度补录'
    remarkInput.dispatchEvent(new Event('input'))
    await flushPromises()

    const saveBtn = Array.from(document.body.querySelectorAll('button')).find((b) => b.textContent?.includes('保存记录'))!
    saveBtn.click()
    await flushPromises()

    expect(createShippingPalletRecordMock).toHaveBeenCalledTimes(1)
    expect(createShippingPalletRecordMock.mock.calls[0][0]).toMatchObject({
      factory_id: 'huaxing',
      ship_date: '2025-08-12',
      customer: 'ZURU',
      pallets: 12,
      remark: '年度补录',
    })

    const searchInput = wrapper.find('input[aria-label="搜索卡板记录"]')
    await searchInput.setValue('MSKU123')
    await searchInput.trigger('keydown.enter')
    await flushPromises()

    const lastQuery = fetchShippingPalletStatsMock.mock.calls.at(-1)?.[0]
    expect(lastQuery).toMatchObject({ q: 'MSKU123' })
  })

  it('drills down, selects detail rows for batch delete, and exports Excel', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    const drillBtn = wrapper.find('button[aria-label="查看 ROSS 柜号明细"]')
    expect(drillBtn.exists()).toBe(true)
    await drillBtn.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('下钻：ROSS')
    expect(wrapper.text()).toContain('MSKU1234567')
    expect(wrapper.text()).not.toContain('HMMU8888888')

    const rowCheckbox = wrapper.find('[aria-label="选择 ROSS MSKU1234567"]')
    await rowCheckbox.trigger('click')
    await flushPromises()

    const batchDeleteBtn = wrapper.findAll('button').find((b) => b.text().includes('删除选中（1）'))!
    expect(batchDeleteBtn.exists()).toBe(true)
    await batchDeleteBtn.trigger('click')
    await flushPromises()

    const confirmBtn = Array.from(document.body.querySelectorAll('button')).find((b) => b.textContent?.includes('确认删除'))!
    confirmBtn.click()
    await flushPromises()

    expect(batchDeleteShippingPalletRecordsMock).toHaveBeenCalledWith([
      { id: 'load-1', factoryId: 'huaxing', originFactoryId: 'huaxing', recordType: 'loading_sheet' },
    ])

    await wrapper.findAll('button').find((b) => b.text().includes('查看全部明细'))!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('MSKU1234567')
    expect(wrapper.text()).toContain('HMMU8888888')

    await wrapper.findAll('button').find((b) => b.text().includes('导出月度对账 Excel'))!.trigger('click')
    await flushPromises()
    expect(exportShippingPalletStatsMock).toHaveBeenCalledTimes(1)
  })

  it('edits summary row inline across customer, spec, counts, price, and estimated cost', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    const editBtn = wrapper.find('button[aria-label="编辑 ROSS 汇总"]')
    expect(editBtn.exists()).toBe(true)
    await editBtn.trigger('click')
    await flushPromises()

    await wrapper.find('input[aria-label="编辑汇总客户"]').setValue('ROSS-VIP')
    await wrapper.find('input[aria-label="编辑汇总卡板规格"]').setValue('标准木卡板 (1200×1000)')
    await wrapper.find('input[aria-label="编辑汇总柜数"]').setValue('3')
    await wrapper.find('input[aria-label="编辑汇总用板数"]').setValue('20')
    await wrapper.find('input[aria-label="编辑汇总参考单价"]').setValue('80')
    await wrapper.find('input[aria-label="编辑汇总预估费用"]').setValue('1550')
    await flushPromises()

    await wrapper.find('button[aria-label="保存 ROSS 汇总修改"]').trigger('click')
    await flushPromises()

    expect(updateShippingPalletGroupMock).toHaveBeenCalledTimes(1)
    expect(updateShippingPalletGroupMock).toHaveBeenCalledWith({
      items: [{ id: 'load-1', factoryId: 'huaxing', originFactoryId: 'huaxing', recordType: 'loading_sheet' }],
      factory_id: 'huaxing',
      customer: 'ROSS-VIP',
      spec: '标准木卡板 (1200×1000)',
      container_count: 3,
      total_pallets: 20,
      unit_price: 80,
      estimated_cost: 1550,
      cost_overridden: true,
    })
  })
})
