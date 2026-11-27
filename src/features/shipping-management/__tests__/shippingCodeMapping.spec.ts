import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ShippingCodeMappingPanel from '../ShippingCodeMappingPanel.vue'

const listGeneratedDocsMock = vi.hoisted(() => vi.fn())
const getGeneratedDocMock = vi.hoisted(() => vi.fn())

vi.mock('@/api/shippingMail', () => ({
  listGeneratedDocs: listGeneratedDocsMock,
  getGeneratedDoc: getGeneratedDocMock,
}))

const SAMPLE_ROWS = [
  {
    date: '2026-01-02',
    contractNo: 'RL-447283-116-1',
    code: '1019461',
    name: '益智积木套装',
    quantity: '2224',
    cartons: '2224',
    perCarton: '1 个',
    category: '塑胶',
    note: 'PO-1019461',
    gross: '1.700',
    net: '0.750',
    volume: '60.048',
    source: '出货登记',
    country: '美国',
    customer: 'SALLING GROUP A/S',
    transport: '成隆达运输',
    containerMode: '柜',
    trip: 'W2柜',
    containerType: '40GP',
    plate: '粤BPB110',
    containerNo: 'GESU6635235',
    sealNo: 'M8021996',
    status: '已同步',
    tone: 'blue',
  },
]

describe('ShippingCodeMappingPanel columns', () => {
  beforeEach(() => {
    listGeneratedDocsMock.mockReset()
    getGeneratedDocMock.mockReset()
    listGeneratedDocsMock.mockResolvedValue([])
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => SAMPLE_ROWS,
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('removes 备注（柜单） and shows 运输公司, 车牌号, 车次, 柜型, 柜号, 封条号 after 客户', async () => {
    const wrapper = mount(ShippingCodeMappingPanel, {
      props: { factoryId: 'huaxing' },
    })

    await flushPromises()

    const headers = wrapper.findAll('thead th').map((th) => th.text().trim())
    expect(headers).not.toContain('备注（柜单）')
    expect(headers).toContain('柜型/T车')

    const customerIdx = headers.indexOf('客户')
    expect(customerIdx).toBeGreaterThan(-1)
    expect(headers.slice(customerIdx + 1, customerIdx + 7)).toEqual([
      '运输公司',
      '车牌号',
      '车次',
      '柜型',
      '柜号',
      '封条号',
    ])

    const rowText = wrapper.find('tbody tr').text()
    expect(rowText).toContain('成隆达运输')
    expect(rowText).toContain('粤BPB110')
    expect(rowText).toContain('W2柜')
    expect(rowText).toContain('40GP')
    expect(rowText).toContain('GESU6635235')
    expect(rowText).toContain('M8021996')

    await wrapper.get('input[aria-label="搜索合同号或货号"]').setValue('GESU6635235')
    await wrapper.findAll('button').find((b) => b.text().trim() === '搜索')!.trigger('click')
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
  })
})
