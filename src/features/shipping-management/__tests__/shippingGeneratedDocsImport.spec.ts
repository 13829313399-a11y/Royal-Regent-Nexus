import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import ShippingGeneratedDocs from '../ShippingGeneratedDocs.vue'
import ShippingSoSchedulePanel from '../ShippingSoSchedulePanel.vue'
import ShippingTruckSchedulePanel from '../ShippingTruckSchedulePanel.vue'
import ShippingTruckExportHistory from '../ShippingTruckExportHistory.vue'
import ShippingLoadingSheetPanel from '../ShippingLoadingSheetPanel.vue'
import ShippingSupplementPanel from '../ShippingSupplementPanel.vue'
import ShippingWorkbookPreviewModal from '../ShippingWorkbookPreviewModal.vue'

const listGeneratedDocsMock = vi.hoisted(() => vi.fn())
const getGeneratedDocMock = vi.hoisted(() => vi.fn())
const searchScheduleProductsMock = vi.hoisted(() => vi.fn())
const draftLoadingSheetMock = vi.hoisted(() => vi.fn())
const draftBulkTruckSheetMock = vi.hoisted(() => vi.fn())
const openGeneratedDocMock = vi.hoisted(() => vi.fn())
const openLoadingSheetMock = vi.hoisted(() => vi.fn())
const listLoadingSheetsMock = vi.hoisted(() => vi.fn().mockResolvedValue([]))
const downloadLoadingSheetMock = vi.hoisted(() => vi.fn())

vi.mock('@/api/shippingMail', () => ({
  listGeneratedDocs: listGeneratedDocsMock,
  getGeneratedDoc: getGeneratedDocMock,
  searchScheduleProducts: searchScheduleProductsMock,
  updateGeneratedDoc: vi.fn(),
  deleteGeneratedDoc: vi.fn(),
  draftLoadingSheet: draftLoadingSheetMock,
  draftBulkTruckSheet: draftBulkTruckSheetMock,
  exportBulkTruckSheet: vi.fn(),
  exportLoadingSheet: vi.fn(),
  getLoadingSheet: vi.fn(),
  listLoadingSheets: listLoadingSheetsMock,
  downloadLoadingSheet: downloadLoadingSheetMock,
  lookupScheduleLines: vi.fn().mockResolvedValue([]),
  openLoadingSheet: openLoadingSheetMock,
  openGeneratedDoc: openGeneratedDocMock,
  downloadGeneratedDoc: vi.fn(),
  draftSupplementSheet: vi.fn(),
  exportSupplementSheet: vi.fn(),
}))

vi.mock('@/api/shippingTasks', () => ({
  listShippingTasks: vi.fn().mockResolvedValue([]),
}))

describe('ShippingGeneratedDocs schedule import fallback', () => {
  it('resolves product lines from factory schedule when booking doc has no lines', async () => {
    vi.stubGlobal('localStorage', {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
    })
    listGeneratedDocsMock.mockResolvedValue([
      {
        id: 'doc-1',
        task_id: 'task-1',
        filename: '1x40HC.pdf',
        module: 'so',
        created_at: '2026-11-23T08:00:00Z',
        header: { contractNo: '166636625' },
      },
    ])
    getGeneratedDocMock.mockResolvedValue({
      id: 'doc-1',
      task_id: 'task-1',
      filename: '1x40HC.pdf',
      module: 'so',
      header: { contractNo: '166636625', bookingNo: '48420550' },
      lines: [],
    })
    searchScheduleProductsMock.mockResolvedValue([
      {
        product_code: 'PLASTIC-48420550',
        product_name: '塑胶玩具',
        quantity: 25020,
        cartons: 2085,
        contract_no: '166636625',
        customer_po: 'CCN4047078-V1',
      },
    ])

    const wrapper = mount(ShippingGeneratedDocs, {
      props: { factoryId: 'huaxing', module: 'so' },
    })

    await flushPromises()

    const importBtn = wrapper.findAll('button').find((btn) => btn.text().includes('导入柜表'))
    expect(importBtn).toBeTruthy()
    await importBtn!.trigger('click')
    await flushPromises()

    const emitted = wrapper.emitted('import-cabinet')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0].lines).toHaveLength(1)
    expect(emitted![0][0].lines[0]).toMatchObject({
      contract: '166636625',
      filingCode: 'PLASTIC-48420550',
      product_code: 'PLASTIC-48420550',
      quantity: 25020,
      cartons: 2085,
      cartonMark: 'CCN4047078-V1',
    })
  })

  it('copies poNo from generated doc header into cabinet sheet PO（箱唛） field', async () => {
    vi.stubGlobal('localStorage', {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
    })
    listGeneratedDocsMock.mockResolvedValue([
      {
        id: 'doc-one',
        task_id: 'task-one',
        filename: 'SO.xls',
        module: 'so',
        created_at: '2026-11-24T08:00:00Z',
        header: { contractNo: 'HAMN00411A', poNo: 'SCAN7446698', bookingNo: 'HKGGC6501802' },
      },
    ])
    getGeneratedDocMock.mockResolvedValue({
      id: 'doc-one',
      task_id: 'task-one',
      filename: 'SO.xls',
      module: 'so',
      header: { contractNo: 'HAMN00411A', poNo: 'SCAN7446698', bookingNo: 'HKGGC6501802' },
      lines: [],
    })
    searchScheduleProductsMock.mockResolvedValue([
      {
        product_code: 'TRICYCLE-6501802',
        product_name: '三轮车',
        quantity: 1200,
        contract_no: 'HAMN00411A',
        customer_po: 'SCAN7446698',
      },
    ])
    draftLoadingSheetMock.mockRejectedValue(new Error('offline'))

    const wrapper = mount(ShippingSoSchedulePanel, {
      props: { factoryId: 'huaxing' },
    })

    await flushPromises()

    const importBtn = wrapper.findAll('button').find((btn) => btn.text().includes('导入柜表'))
    expect(importBtn).toBeTruthy()
    await importBtn!.trigger('click')
    await flushPromises()

    const poLabels = wrapper.findAll('label').filter((el) => el.text().trim().startsWith('PO（箱唛）'))
    expect(poLabels.length).toBeGreaterThanOrEqual(2)
    const cabinetPoInput = poLabels[poLabels.length - 1]!.get('input')
    expect((cabinetPoInput.element as HTMLInputElement).value).toBe('SCAN7446698')
  })

  it('displays email_name on generated doc pills when email_name is available', async () => {
    vi.stubGlobal('localStorage', {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
    })
    listGeneratedDocsMock.mockResolvedValue([
      {
        id: 'doc-mail-1',
        task_id: 'task-mail-1',
        filename: '车的排出货表_盐田散货_EMLSO202611.xlsx',
        email_name: 'Booking Amendment EMLSO202611 - revised again',
        module: 'truck_bulk',
        created_at: '2026-11-24T08:00:00Z',
        header: { contractNo: 'HAMN00411A' },
      },
      {
        id: 'doc-mail-2',
        task_id: 'task-mail-2',
        filename: '成隆达运输，出盐田_48420550.xls',
        module: 'so_dk',
        created_at: '2026-11-24T08:00:00Z',
        header: { contractNo: '166636625' },
      },
    ])
    getGeneratedDocMock.mockResolvedValue({
      id: 'doc-mail-1',
      task_id: 'task-mail-1',
      filename: '车的排出货表_盐田散货_EMLSO202611.xlsx',
      email_name: 'Booking Amendment EMLSO202611 - revised again',
      module: 'truck_bulk',
      header: { contractNo: 'HAMN00411A' },
      lines: [],
    })

    const wrapper = mount(ShippingGeneratedDocs, {
      props: { factoryId: 'huaxing', module: 'truck' },
    })

    await flushPromises()

    const pillTexts = wrapper.findAll('button span.truncate').map((el) => el.text())
    expect(pillTexts).toEqual([
      'Booking Amendment EMLSO202611 - revised again',
      '成隆达运输，出盐田_48420550.xls',
    ])
  })

  it('populates bulk truck table rows from imported schedule lines instead of leaving a blank row', async () => {
    vi.stubGlobal('localStorage', {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
    })
    listGeneratedDocsMock.mockResolvedValue([
      {
        id: 'doc-cosco',
        task_id: 'task-cosco',
        filename: '车的排出货表_盐田散货_COSU9508290536.xlsx',
        email_name: 'SO_COSU9508290536_40HQ_1643箱.pdf',
        module: 'truck_bulk',
        created_at: '2026-11-24T08:00:00Z',
        header: { contractNo: 'EWB26101', bookingNo: 'COSU9508290536', brandNote: 'CARGO SERVICES', country: '英国' },
      },
    ])
    getGeneratedDocMock.mockResolvedValue({
      id: 'doc-cosco',
      task_id: 'task-cosco',
      filename: '车的排出货表_盐田散货_COSU9508290536.xlsx',
      email_name: 'SO_COSU9508290536_40HQ_1643箱.pdf',
      module: 'truck_bulk',
      header: { contractNo: 'EWB26101', bookingNo: 'COSU9508290536', brandNote: 'CARGO SERVICES', country: '英国', poNo: 'CD5709769925' },
      lines: [],
    })
    searchScheduleProductsMock.mockResolvedValue([
      {
        product_code: 'KW-9508290536',
        product_name: '家居厨房用品',
        quantity: 1200,
        gross_weight: 12000,
        contract_no: 'EWB26101',
        customer_po: 'CD5709769925',
        country: '英国',
        so_number: 'COSU9508290536',
      },
    ])
    draftBulkTruckSheetMock.mockResolvedValue({
      taskId: 'task-cosco',
      header: {
        toNames: ['苏迪', '罗梓良'],
        fromName: '农建壮',
        sheetDate: '2026-07-17',
        vehicle: 'W218',
        transport: '建联派',
        truckType: '3吨',
        tradeTerm: 'EXW',
        tableName: '建联派运输，出盐田',
        cutoff: '2026-07-17',
        originPort: '盐田',
        warehouseNo: '',
        truckCount: '1',
        brandName: 'CARGO SERVICES',
        brandNote: 'CARGO SERVICES',
        tradingHouse: '',
        shipper: '华兴玩具制品（河源）有限公司',
        plate: '',
        consignee: '',
        country: '英国',
        arrivalCutoff: '2026-07-18T12:00',
        consolidator: '',
        scheduleText: '',
      },
      lines: [
        {
          id: 'blank-1', tradingHouse: 'ZURU', contract: '', filingCode: '', declareCode: '', name: '',
          coefficient: null, quantity: null, cartons: null, boards: '', grossWeight: null, netWeight: null,
          cbm: null, country: '', grossPerCarton: null, netPerCarton: null, cbmPerCarton: null, brand: '',
          so: 'COSU9508290536', po: '', shippingNote: '', remark: '',
        },
      ],
      totals: { quantity: 0, cartons: 0, grossWeight: 0, netWeight: 0, cbm: 0 },
    })

    const wrapper = mount(ShippingTruckSchedulePanel, {
      props: { factoryId: 'huaxing' },
      global: {
        stubs: {
          ShippingTruckExportHistory: true,
        },
      },
    })

    await flushPromises()

    const importBtn = wrapper.findAll('button').find((btn) => btn.text().includes('导入盐田散货W车'))
    expect(importBtn).toBeTruthy()
    await importBtn!.trigger('click')
    await flushPromises()

    const soLabel = wrapper.findAll('label').find((el) => el.text().trim().startsWith('订舱号/SO'))
    expect((soLabel!.get('input').element as HTMLInputElement).value).toBe('COSU9508290536')

    const rowInputs = wrapper.findAll('tbody tr:first-child input').map((input) => (input.element as HTMLInputElement).value)
    expect(rowInputs).toContain('EWB26101')
    expect(rowInputs).toContain('KW-9508290536')
    expect(rowInputs).toContain('家居厨房用品')
    expect(rowInputs).toContain('1200')
    expect(rowInputs).toContain('12000')
    expect(rowInputs).toContain('英国')
    expect(rowInputs).toContain('CARGO SERVICES')
  })

  it('opens exported truck sheet locally when clicking 打开', async () => {
    vi.stubGlobal('localStorage', {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
    })
    listGeneratedDocsMock.mockResolvedValue([
      {
        id: 'gen-truck-1',
        task_id: 'task-1',
        filename: 'KW-9508290536.xls',
        module: 'truck_export',
        created_at: '2026-11-24T08:53:00Z',
        header: {},
      },
    ])
    openGeneratedDocMock.mockResolvedValue({
      opened: true,
      path: 'C:\\Temp\\KW-9508290536.xls',
      filename: 'KW-9508290536.xls',
      sheets: [
        {
          name: '散货送仓',
          rows: [
            ['合约', '备案货号', '数量'],
            ['EWB26101', 'KW-9508290536', '1200'],
          ],
        },
      ],
    })

    const wrapper = mount(ShippingTruckExportHistory, {
      props: { factoryId: 'huaxing' },
    })

    await flushPromises()
    const openBtn = wrapper.findAll('button').find((btn) => btn.text().trim() === '打开')
    expect(openBtn).toBeTruthy()
    await openBtn!.trigger('click')
    await flushPromises()

    expect(openGeneratedDocMock).toHaveBeenCalledWith('huaxing', 'gen-truck-1')
    expect(wrapper.find('[role="dialog"][aria-label="表格预览"]').exists()).toBe(false)
  })

  it('renders 下载 button before 查看 and 打开 in 已导出柜货单 and downloads the sheet', async () => {
    vi.stubGlobal('localStorage', {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
    })
    listLoadingSheetsMock.mockResolvedValue([
      {
        id: 'load-1',
        number: 'W1',
        sheetDate: '2026-11-23',
        filename: 'ROSS-279188253.xls',
        filingCodes: ['ROSS-279188253'],
        soNo: '279188253',
        contractNo: '298379137',
        createdAt: '2026-11-23T17:13:00Z',
        totals: {},
      },
    ])
    downloadLoadingSheetMock.mockResolvedValue(new Blob(['xls-bytes'], { type: 'application/vnd.ms-excel' }))
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn().mockReturnValue('blob:mock'),
      revokeObjectURL: vi.fn(),
    })

    const wrapper = mount(ShippingLoadingSheetPanel, {
      props: { factoryId: 'huaxing' },
    })

    await flushPromises()

    const actionButtons = wrapper.findAll('tbody td:last-child button').map((btn) => btn.text().trim())
    expect(actionButtons).toEqual(['下载', '查看', '打开', '异常'])

    await wrapper.findAll('tbody td:last-child button')[0]!.trigger('click')
    await flushPromises()
    expect(downloadLoadingSheetMock).toHaveBeenCalledWith('huaxing', 'load-1')
  })

  it('keeps email name on top pills while using filing-code filename on download links', async () => {
    vi.stubGlobal('localStorage', {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
    })
    listGeneratedDocsMock.mockResolvedValue([
      {
        id: 'doc-hkgm',
        task_id: 'task-hkgm',
        filename: 'GDSM-HKGM002686.xlsx',
        email_name: '01_SO-MC605368_HMM.pdf',
        module: 'truck_bulk',
        created_at: '2026-11-24T08:00:00Z',
        header: { bookingNo: 'HKGM00268600' },
      },
    ])
    getGeneratedDocMock.mockResolvedValue({
      id: 'doc-hkgm',
      task_id: 'task-hkgm',
      filename: 'GDSM-HKGM002686.xlsx',
      email_name: '01_SO-MC605368_HMM.pdf',
      module: 'truck_bulk',
      header: { bookingNo: 'HKGM00268600', filingCode: 'GDSM-HKGM002686' },
      lines: [],
    })

    const wrapper = mount(ShippingGeneratedDocs, {
      props: { factoryId: 'huaxing', module: 'truck' },
    })

    await flushPromises()

    expect(wrapper.findAll('button span.truncate').map((el) => el.text())).toEqual(['01_SO-MC605368_HMM.pdf'])
    const downloadLink = wrapper.find('a[download]')
    expect(downloadLink.exists()).toBe(true)
    expect(downloadLink.attributes('download')).toBe('GDSM-HKGM002686.xlsx')
  })

  it('opens 已生成补料单 locally when clicking 打开', async () => {
    vi.stubGlobal('localStorage', {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
    })
    listGeneratedDocsMock.mockResolvedValue([
      {
        id: 'supp-1',
        task_id: 'task-supp-1',
        module: 'supplement',
        filename: 'TRICYCLE-6501802.xlsx',
        created_at: '2026-11-24T10:12:00Z',
        header: {},
      },
    ])
    openGeneratedDocMock.mockResolvedValue({
      opened: true,
      path: 'C:/temp/TRICYCLE-6501802.xlsx',
      filename: 'TRICYCLE-6501802.xlsx',
      sheets: [
        {
          name: 'Shipment Advice',
          rows: [
            ['Item#', 'Pcs', 'Ctns', 'Sales Conf#'],
            ['TRICYCLE-6501802', '5', '1.667', 'HAMN00411A'],
          ],
        },
      ],
    })

    const wrapper = mount(ShippingSupplementPanel, {
      props: { factoryId: 'huaxing' },
    })

    await flushPromises()

    const openBtn = wrapper.findAll('button').find((btn) => btn.text().trim() === '打开')
    expect(openBtn).toBeDefined()
    await openBtn!.trigger('click')
    await flushPromises()

    expect(openGeneratedDocMock).toHaveBeenCalledWith('huaxing', 'supp-1')
    expect(wrapper.find('[role="dialog"][aria-label="表格预览"]').exists()).toBe(false)
  })

  it('renders merged cells, fill color, borders, and bold font from styled cells payload', async () => {
    const wrapper = mount(ShippingWorkbookPreviewModal, {
      props: {
        filename: 'TRICYCLE-6501802.xlsx',
        sheets: [
          {
            name: '1',
            rows: [['更正补料1']],
            colWidths: [90, 120],
            rowHeights: [28],
            cells: [
              [
                {
                  v: '更正补料1',
                  rs: 2,
                  cs: 2,
                  bg: '#ffff00',
                  bold: true,
                  border: { b: '1px solid #000000' },
                },
                { v: '', skip: true },
              ],
            ],
          },
        ],
      },
    })

    const td = wrapper.find('tbody td')
    expect(td.exists()).toBe(true)
    expect(td.text()).toBe('更正补料1')
    expect(td.attributes('rowspan')).toBe('2')
    expect(td.attributes('colspan')).toBe('2')
    const styleAttr = td.attributes('style') || ''
    expect(styleAttr).toMatch(/background-color:\s*(rgb\(255,\s*255,\s*0\)|#ffff00)/i)
    expect(styleAttr).toMatch(/border-bottom:\s*1px solid (rgb\(0,\s*0,\s*0\)|#000000)/i)
    expect(styleAttr).toMatch(/font-weight:\s*700/i)
  })
})
