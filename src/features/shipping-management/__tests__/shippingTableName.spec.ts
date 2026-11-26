import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import ShippingBulkTruckSheetPanel from '../ShippingBulkTruckSheetPanel.vue'

const draftBulkTruckSheetMock = vi.hoisted(() => vi.fn())
const listShippingTasksMock = vi.hoisted(() => vi.fn())

vi.mock('@/api/shippingMail', () => ({
  draftBulkTruckSheet: draftBulkTruckSheetMock,
  exportBulkTruckSheet: vi.fn(),
  searchScheduleProducts: vi.fn().mockResolvedValue([]),
  listGeneratedDocs: vi.fn().mockResolvedValue([]),
}))

vi.mock('@/api/shippingTasks', () => ({
  listShippingTasks: listShippingTasksMock,
}))

describe('ShippingBulkTruckSheetPanel tableName formatting', () => {
  it('formats 表格名称 as 运输公司+运输，出+出港口 and updates live on edits', async () => {
    listShippingTasksMock.mockResolvedValue([
      { id: 'task-1', so_number: 'SOHX261101', port: '盐田', planned_ship_date: '2026-12-08' },
    ])
    draftBulkTruckSheetMock.mockResolvedValue({
      taskId: 'task-1',
      header: {
        toNames: ['苏迪', '罗梓良'],
        fromName: '农建壮',
        sheetDate: '2026-11-23',
        vehicle: 'W15',
        transport: '成隆达',
        truckType: '3T',
        tradeTerm: 'EXW',
        tableName: '盐客上车W15车',
        cutoff: '2026-12-06',
        originPort: '盐田',
        warehouseNo: '2',
        truckCount: '1',
        brandName: 'BUZZBEE',
        brandNote: 'BUZZBEE',
        tradingHouse: 'BUZZBEE',
        shipper: '华兴玩具制品（河源）有限公司',
        plate: '粤BE7959',
        consignee: '',
        country: '美国',
        arrivalCutoff: '',
        consolidator: '',
        scheduleText: '',
      },
      lines: [],
      totals: { quantity: 0, cartons: 0, grossWeight: 0, netWeight: 0, cbm: 0 },
    })

    const wrapper = mount(ShippingBulkTruckSheetPanel, {
      props: {
        factoryId: 'huaxing',
        initialTaskId: 'task-1',
        initialHeader: {
          transportCompany: '成隆达',
          originPort: '盐田',
          tableName: '盐客上车W15车',
        },
      },
      global: {
        stubs: {
          ShippingTruckExportHistory: true,
        },
      },
    })

    await flushPromises()

    const findInputByLabel = (labelText: string) => {
      const label = wrapper.findAll('label').find((item) => item.text().trim().startsWith(labelText))
      expect(label, `missing label ${labelText}`).toBeTruthy()
      return label!.get('input')
    }

    const tableNameInput = findInputByLabel('表格名称')
    const transportInput = findInputByLabel('运输公司')
    const portSelect = wrapper.findAll('label').find((item) => item.text().trim().startsWith('出港口'))!.get('select')

    expect((tableNameInput.element as HTMLInputElement).value).toBe('成隆达运输，出盐田')

    await transportInput.setValue('建联派运输')
    expect((tableNameInput.element as HTMLInputElement).value).toBe('建联派运输，出盐田')

    await portSelect.setValue('蛇口')
    expect((tableNameInput.element as HTMLInputElement).value).toBe('建联派运输，出蛇口')

    await portSelect.setValue('')
    expect((tableNameInput.element as HTMLInputElement).value).toBe('建联派运输')

    wrapper.unmount()
  })
})
