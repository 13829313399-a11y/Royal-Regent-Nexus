import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CartonSupplierView from '../CartonSupplierView.vue'
import CartonSupplierManagementView from '../CartonSupplierManagementView.vue'
import CartonReceiptAllocations from '@/components/CartonReceiptAllocations.vue'
import type { PortalWorkspace } from '@/api/cartonSupplierPortal'
const api = vi.hoisted(() => ({ memberships: vi.fn(), workspace: vi.fn(), accept: vi.fn(), ship: vi.fn(), receive: vi.fn(), members: vi.fn(), member: vi.fn(), upload: vi.fn(), download: vi.fn() }))
const can = vi.hoisted(() => vi.fn((_permission: string) => true))
vi.mock('@/api/cartonSupplierPortal', () => ({ cartonSupplierPortalApi: api }))
vi.mock('@/api/cartonPositions', () => ({ cartonPositionsApi: { locations: vi.fn(async () => [{ id: 'BIN-A', factory_id: 'huaxing', warehouse: 'A', bin_code: '01', label: 'A / 01', status: 'ACTIVE' }]) } }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ can }) }))
vi.mock('@/stores/app', () => ({ useAppStore: () => ({ activeProductionFactory: { id: 'huaxing' } }) }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: { factory: 'huaxing' } }) }))
function fixture(): PortalWorkspace {
  return { factory_id: 'huaxing', supplier_name: '河源东康', orders: [{ id: 'ORDER-A', order_no: 'ORDER-A', customer_name: 'Dickie', contract_no: 'SC-A', customer_po: 'PO-A', item_no: 'ITEM-A', product_name: '产品', status: 'PENDING_SUPPLIER', issue_id: 'ISSUE-A', document_no: 'ORDER-A-P00', planned_date: '2026-09-25', awaiting_issue: false, attachments: [], lines: ['外箱', '平卡'].map((name, index) => ({ id: `LINE-${index}`, line_no: index+1, child_no: `ORDER-A/0${index+1}`, packaging_type: name, paper_quality: 'A33', specification: '10*20', dimension_unit: 'cm', unit: index ? '张' : '个', required_quantity: '100', received_quantity: '0', in_transit_quantity: '0', remaining_to_ship: '100', accepted: true, commitment_revision: 1, promised_date: '2026-09-25' })) }], shipments: [{ id: 'SHIP-A', delivery_note_no: 'DN-A', delivery_date: '2026-09-21', status: 'SENT', revision: 1, created_at: '', confirmed_at: '', acceptance_date: null, acceptance_lines: [], lines: [0,1].map(index => ({ id: `SL-${index}`, order_line_id: `LINE-${index}`, order_no: 'ORDER-A', contract_no: 'SC-A', customer_po: 'PO-A', item_no: 'ITEM-A', customer_name: 'Dickie', child_no: `ORDER-A/0${index+1}`, packaging_type: index ? '平卡' : '外箱', paper_quality: 'A33', specification: '10*20', unit: '个', quantity: '10', unit_price: '2', currency: 'CNY' })) }] }
}
const options = { global: { stubs: { AccountMenu: true, RouterLink: { template: '<a><slot /></a>' }, CartonReceiptAllocations: true } } }
beforeEach(() => { vi.resetAllMocks(); can.mockReturnValue(true); api.memberships.mockResolvedValue([{ factory_id: 'huaxing', supplier_name: '河源东康' }]); api.workspace.mockResolvedValue(fixture()); api.members.mockResolvedValue([]); api.ship.mockResolvedValue({ id: 'NEW' }); api.receive.mockResolvedValue({ id: 'SHIP-A' }) })
describe('supplier collaboration entry', () => {
  it('shows an unbound account message without requesting an arbitrary factory workspace', async () => {
    api.memberships.mockResolvedValue([])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('尚未开通供应商协同')
    expect(api.workspace).not.toHaveBeenCalled(); wrapper.unmount()
  })
  it('submits separately selected paper identities and actual shipment quantities', async () => {
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.get('input[aria-label="选择发货 ORDER-A/01"]').setValue(true)
    await wrapper.get('input[aria-label="ORDER-A/01 发货数量"]').setValue(4)
    await wrapper.get('input[aria-label="选择发货 ORDER-A/02"]').setValue(true)
    await wrapper.get('input[aria-label="ORDER-A/02 发货数量"]').setValue(8)
    await wrapper.get('input[aria-label="供应商送货单号"]').setValue('DN-NEW')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.ship).toHaveBeenCalledWith(expect.objectContaining({ factory_id: 'huaxing', delivery_note_no: 'DN-NEW', lines: [{ order_line_id: 'LINE-0', issue_id: 'ISSUE-A', quantity: 4 }, { order_line_id: 'LINE-1', issue_id: 'ISSUE-A', quantity: 8 }] }))
    expect(wrapper.get<HTMLInputElement>('input[aria-label="供应商送货单号"]').element.value).toBe('')
    expect(wrapper.get('[role="status"]').text()).toContain('尚未计入库存'); wrapper.unmount()
  })
  it('blocks stale unissued commitments and retains values on a shipment error', async () => {
    const data = fixture(); data.orders[0]!.awaiting_issue = true
    api.workspace.mockResolvedValue(data)
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(wrapper.text()).toContain('旧承诺暂停执行')
    expect(wrapper.get('input[aria-label="选择发货 ORDER-A/01"]').attributes('disabled')).toBeDefined()
    data.orders[0]!.awaiting_issue = false; api.workspace.mockResolvedValue(structuredClone(data))
    await wrapper.findAll('button').find(button => button.text() === '刷新')!.trigger('click'); await flushPromises()
    api.ship.mockRejectedValue(new Error('当前剩余未送不足'))
    await wrapper.get('input[aria-label="选择发货 ORDER-A/01"]').setValue(true)
    await wrapper.get('input[aria-label="ORDER-A/01 发货数量"]').setValue(7)
    await wrapper.get('input[aria-label="供应商送货单号"]').setValue('DN-RETRY')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('当前剩余未送不足')
    expect(wrapper.get<HTMLInputElement>('input[aria-label="ORDER-A/01 发货数量"]').element.value).toBe('7'); wrapper.unmount()
  })
  it('requires a commitment before dispatch and sends the issued version and expected revision', async () => {
    const data = fixture(); data.orders[0]!.lines[0]!.accepted = false
    api.workspace.mockResolvedValue(data)
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(wrapper.get('input[aria-label="选择发货 ORDER-A/01"]').attributes('disabled')).toBeDefined()
    await wrapper.get('input[aria-label="ORDER-A/01 承诺交期"]').setValue('2026-09-28')
    await wrapper.findAll('button').find(button => button.text() === '确认接单')!.trigger('click'); await flushPromises()
    expect(api.accept).toHaveBeenCalledWith(expect.objectContaining({ id: 'LINE-0', commitment_revision: 1 }), expect.objectContaining({ issue_id: 'ISSUE-A' }), 'huaxing', '2026-09-28'); wrapper.unmount()
  })
})
describe('internal supplier collaboration', () => {
  it('hides privileged member and attachment controls for a receipt-only warehouse operator', async () => {
    can.mockImplementation(permission => ['carton_procurement:read', 'carton_procurement:receipt_write', 'carton_procurement:inventory_write'].includes(permission))
    const wrapper = mount(CartonSupplierManagementView, options); await flushPromises()
    expect(wrapper.text()).not.toContain('供应商成员绑定')
    expect(wrapper.find('input[type="file"]').exists()).toBe(false)
    expect(api.members).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('核实实际收到'); wrapper.unmount()
  })
  it('allows explicit all-zero non-arrival with reasons and closes a successful confirmation before refresh', async () => {
    const wrapper = mount(CartonSupplierManagementView, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '核实实际收到')!.trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('确认整单未收到并退回')
    for (const input of wrapper.findAll('input[aria-label$="差异原因"]')) await input.setValue('货物尚未实际送到')
    api.workspace.mockRejectedValueOnce(new Error('台账刷新失败'))
    await wrapper.get('[role="dialog"]').trigger('submit'); await flushPromises()
    expect(api.receive).toHaveBeenCalledWith('SHIP-A', expect.objectContaining({ expected_revision: 1, lines: [expect.objectContaining({ shipment_line_id: 'SL-0', received_quantity: 0, difference_reason: '货物尚未实际送到' }), expect.objectContaining({ shipment_line_id: 'SL-1', received_quantity: 0 })] }))
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('[role="status"]').text()).toContain('仓库核实已保存'); wrapper.unmount()
  })
  it('retains partial quantities and differences on atomic receipt failure', async () => {
    api.receive.mockRejectedValue(new Error('单价或仓位无效，本次未入库'))
    const wrapper = mount(CartonSupplierManagementView, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '核实实际收到')!.trigger('click')
    await wrapper.get('input[aria-label="SL-0 实收"]').setValue(6)
    await wrapper.get('input[aria-label="SL-0 差异原因"]').setValue('短收四件待核实')
    wrapper.findAllComponents(CartonReceiptAllocations)[0]!.vm.$emit('update:modelValue', [{ location_id: 'BIN-A', quantity: 6 }])
    await wrapper.get('[role="dialog"]').trigger('submit'); await flushPromises()
    expect(wrapper.get<HTMLInputElement>('input[aria-label="SL-0 实收"]').element.value).toBe('6')
    expect(wrapper.get('[role="dialog"]').text()).toContain('本次未入库'); wrapper.unmount()
  })
  it('requires complete valid allocations for positive effective receipts before sending', async () => {
    const wrapper = mount(CartonSupplierManagementView, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '核实实际收到')!.trigger('click')
    await wrapper.get('input[aria-label="SL-0 实收"]').setValue(6)
    for (const input of wrapper.findAll('input[aria-label$="差异原因"]')) await input.setValue('本次到货差异待核实')
    await wrapper.get('[role="dialog"]').trigger('submit'); await flushPromises()
    expect(api.receive).not.toHaveBeenCalled()
    expect(wrapper.get('[role="dialog"]').text()).toContain('必须选择有效仓位')
    const allocations = wrapper.findAllComponents(CartonReceiptAllocations)[0]!
    allocations.vm.$emit('update:modelValue', [{ location_id: 'BIN-A', quantity: 5 }])
    await wrapper.get('[role="dialog"]').trigger('submit'); await flushPromises()
    expect(api.receive).not.toHaveBeenCalled()
    expect(wrapper.get('[role="dialog"]').text()).toContain('合计必须等于')
    allocations.vm.$emit('update:modelValue', [{ location_id: 'unknown-bin', quantity: 6 }])
    await wrapper.get('[role="dialog"]').trigger('submit'); await flushPromises()
    expect(api.receive).not.toHaveBeenCalled()
    allocations.vm.$emit('update:modelValue', [{ location_id: 'BIN-A', quantity: 6 }])
    await wrapper.get('[role="dialog"]').trigger('submit'); await flushPromises()
    expect(api.receive).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false); wrapper.unmount()
  })
})
