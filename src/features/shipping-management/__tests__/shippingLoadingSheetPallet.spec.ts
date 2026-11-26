import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ShippingLoadingSheetPanel from '../ShippingLoadingSheetPanel.vue'
import type { LoadingDraft } from '@/api/shippingMail'

const exportLoadingSheetMock = vi.hoisted(() => vi.fn())
const listLoadingSheetsMock = vi.hoisted(() => vi.fn())

vi.mock('@/api/shippingMail', () => ({
  deleteLoadingSheet: vi.fn(),
  downloadLoadingSheet: vi.fn(),
  draftLoadingSheet: vi.fn(),
  exportLoadingSheet: exportLoadingSheetMock,
  getLoadingSheet: vi.fn(),
  listLoadingSheets: listLoadingSheetsMock,
  lookupScheduleLines: vi.fn().mockResolvedValue([]),
  openLoadingSheet: vi.fn(),
  searchScheduleProducts: vi.fn().mockResolvedValue([]),
}))

vi.mock('@/api/shippingTasks', () => ({
  listShippingTasks: vi.fn().mockResolvedValue([]),
}))

const SAMPLE_DRAFT: LoadingDraft = {
  number: 'W1',
  taskId: 'task-1',
  totals: { quantity: 600, cartons: 50, grossWeight: 200, netWeight: 150, cbm: 2.5 },
  header: {
    shipper: '华兴玩具制品（河源）有限公司',
    consignee: 'FLEXPORT',
    tradingCompany: 'DK',
    soNo: '2171173340',
    contractNo: 'PE264516',
    filingCode: '950590-2171173340',
    vessel: 'OOCL LONDON',
    voyage: '124E',
    containerType: '40HQ',
    cutoff: '2026-07-11T22:00',
    sheetDate: '2026-11-24',
    preparer: '农建壮',
    brandNote: 'FLEXPORT',
    originPort: '盐田',
    transportCompany: '成隆达',
    tableName: '成隆达运输，出盐田',
    number: 'W1',
    plate: '',
    containerNo: '',
    sealNo: '',
    tareWeight: '',
    destinationCountry: '美国',
    bookingDate: '',
    photoNote: '注，要照相',
    department: 'W',
  },
  lines: [
    {
      id: 'line-1',
      tradingCompany: 'DK',
      contract: 'PE264516',
      filingCode: '950590-2171173340',
      declareCode: '950590-2171173340',
      coefficient: 12,
      quantity: 600,
      cartons: 50,
      grossWeight: 200,
      netWeight: 150,
      cbm: 2.5,
      category: '塑胶',
      grossPerCarton: 4,
      netPerCarton: 3,
      description: '万圣节装饰品 (HS 9505.90)',
      department: 'W',
      pallet: null,
      cartonMark: 'FLXCB-1712593',
    },
  ],
}

describe('ShippingLoadingSheetPanel pallet column', () => {
  beforeEach(() => {
    exportLoadingSheetMock.mockReset()
    listLoadingSheetsMock.mockReset()
    listLoadingSheetsMock.mockResolvedValue([])
    exportLoadingSheetMock.mockResolvedValue(new Blob(['xls-bytes']))
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn().mockReturnValue('blob:mock-xls'),
      revokeObjectURL: vi.fn(),
    })
  })

  it('renders 卡板数量 beside 部门, totals it live, and sends pallet count on export', async () => {
    const wrapper = mount(ShippingLoadingSheetPanel, {
      props: {
        factoryId: 'huaxing',
        initialDraft: JSON.parse(JSON.stringify(SAMPLE_DRAFT)),
      },
    })

    await flushPromises()

    const headers = wrapper.findAll('thead th').map((th) => th.text().trim())
    const deptIdx = headers.indexOf('部门')
    expect(deptIdx).toBeGreaterThan(-1)
    expect(headers[deptIdx + 1]).toBe('卡板数量')

    const palletInput = wrapper.find('input[aria-label="卡板数量"]')
    expect(palletInput.exists()).toBe(true)
    await palletInput.setValue('8')
    await flushPromises()

    const totalCells = wrapper.find('tbody tr:last-child').findAll('td')
    expect(totalCells.at(-2)?.text().trim()).toBe('8')

    await wrapper.findAll('button').find((b) => b.text().includes('导出柜货单'))!.trigger('click')
    await flushPromises()

    expect(exportLoadingSheetMock).toHaveBeenCalledTimes(1)
    const exportedDraft = exportLoadingSheetMock.mock.calls[0][1]
    expect(exportedDraft.lines[0].pallet).toBe(8)
  })
})
