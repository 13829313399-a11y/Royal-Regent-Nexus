import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { Output, SubOrder, SubWorkspace } from '@/api/fabricSubcontract'
import FabricSubcontractOrderForm from '../FabricSubcontractOrderForm.vue'
import FabricSubcontractActionForm from '../FabricSubcontractActionForm.vue'
import FabricSubcontractProgress from '../FabricSubcontractProgress.vue'
import { sendableSubcontractInputs } from '../operations'

const data: SubWorkspace = {
  revision: 2, can_correct: true, can_operate: true, can_manage: true, locations: [], orders: [], stock: [],
  materials: [{ id:'output', item_code:'BIND', item_name:'黑色捆条', unit:'米', material_category:'ACCESSORY' }],
  processors: [{ id:'factory', code:'F1', name:'加工厂一', active:true, processes:['捆条','电绣'], phone:'', contact:'' }],
}

describe('subcontract ledger progress', () => {
  const output: Output = { ...data.materials[0]!, planned:'120', delivered:'100', received:'90', available:'40',
    outstanding:'30', uncounted:'10', undelivered:'20' }
  const order: SubOrder = { id:'order', process:'捆条', processor:data.processors[0]!, business_date:'2026-01-01',
    due_date:'2026-11-28', source_no:'', inputs:[], outputs:[output], events:[], batches:[], other_movements:[] }
  it('shows 75% counted for a delivery of 100 with 90 actually received, including split quantities', () => {
    const row = mount(FabricSubcontractProgress, { props:{order, output} })
    expect(row.text()).toContain('到货待点收')
    expect(row.text()).toContain('已收 75%')
    expect(row.get('[role=progressbar]').attributes()).toMatchObject({
      'aria-valuenow':'75', 'aria-valuetext':'已收 90 米，应回 120 米，待点收 10 米，厂欠 20 米',
    })
  })
  it('tracks each product in its own unit, and updates when a receipt is corrected', async () => {
    const other: Output = { ...output, id:'second', item_code:'B2', unit:'件', planned:'5', delivered:'5',
      received:'5', available:'0', outstanding:'0', uncounted:'0', undelivered:'0' }
    const row = mount(FabricSubcontractProgress, {props:{ order:{...order, outputs:[output, other]}, output:other }})
    expect(row.get('[role=progressbar]').attributes('aria-valuenow')).toBe('100')
    expect(row.text()).toContain('已收 5 件')
    expect(row.text()).not.toContain('领用')
    await row.setProps({output:{...other, received:'0', uncounted:'5', outstanding:'5'}})
    expect(row.text()).toContain('到货待点收')
    expect(row.get('[role=progressbar]').attributes('aria-valuenow')).toBe('0')
  })
  it('distinguishes an order awaiting raw dispatch from a shipped order at zero return progress', async () => {
    const pending: Output = {...output, delivered:'0', received:'0', available:'0', outstanding:'120', uncounted:'0', undelivered:'120'}
    const batch = {...data.materials[0]!, lot:'L', roll_no:'R', location_id:'bin', location:'A', sent:'0', planned:'12'}
    const row = mount(FabricSubcontractProgress, {props:{output:pending, order:{...order, outputs:[pending], inputs:[batch]}}})
    expect(row.text()).toContain('已选料，待发出')
    await row.setProps({order:{...order, outputs:[pending], inputs:[{...batch,sent:'12'}]}})
    expect(row.text()).toContain('已发料，待厂送回')
    expect(row.get('[role=progressbar]').attributes('aria-valuenow')).toBe('0')
  })
})

describe('fabric subcontract order entry', () => {
  it('preserves decimal input in original units when creating an order', async () => {
    const wrapper = mount(FabricSubcontractOrderForm, {props:{data, locked:false}})
    const selectors = wrapper.findAll('select')
    await selectors[1]!.setValue('factory')
    await selectors[2]!.setValue('output')
    await wrapper.get('input[inputmode=decimal]').setValue('1000.000001')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('save')?.[0]).toEqual(['/orders', expect.objectContaining({
      processor_id:'factory', outputs:[{ id:'output', quantity:'1000.000001' }], inputs:[],
    })])
  })
  it.each(['电绣','丝印'])('keeps the Engineering processor read-only for %s', async process => {
    const wrapper = mount(FabricSubcontractOrderForm, {props:{data, locked:false}})
    await wrapper.get('select').setValue(process)
    expect(wrapper.get('input[value="待工程系统带出"]').attributes()).toHaveProperty('readonly')
    expect(wrapper.get('button[type=submit]').attributes()).toHaveProperty('disabled')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('save')).toBeUndefined()
  })
})

describe('subcontract delivery and counting', () => {
  const warehouse = { ...data, locations:[{id:'bin', label:'辅料一仓', category:'ACCESSORY', status:'ACTIVE'}] }
  const order: SubOrder = { id:'order', process:'捆条', processor:data.processors[0]!, business_date:'2026-01-01',
    due_date:'2026-11-28', source_no:'ENG', inputs:[], events:[], batches:[], other_movements:[],
    outputs:[{...data.materials[0]!, planned:'1000', delivered:'0', undelivered:'1000', received:'0', uncounted:'0', outstanding:'1000', available:'0'}],
  }
  async function openDelivery() {
    const wrapper = mount(FabricSubcontractActionForm, {props:{data:warehouse, order, stage:'DELIVER', locked:false}})
    await wrapper.get('input[inputmode=decimal]').setValue('600')
    await wrapper.get('input[maxlength="128"]').setValue('SH-1')
    await wrapper.get('input[aria-label="回仓仓位"]').setValue('辅料一仓')
    return wrapper
  }
  it('offers only planned batches that can actually be sent, up to current stock or the remaining plan', async () => {
    const batch = { ...data.materials[0]!, id:'raw', lot:'L1', roll_no:'01', location_id:'bin', location:'布料一仓' }
    const inputs = [{ ...batch, planned:'30', sent:'5.5' }]
    expect(sendableSubcontractInputs(inputs, [])).toEqual([])
    expect(sendableSubcontractInputs(inputs, [{...batch, available:'30'}])[0]?.max).toBe('24.5')
    const wrapper = mount(FabricSubcontractActionForm, {props:{
      data:{ ...warehouse, stock:[{ ...batch, available:'8.25' }] }, order:{ ...order, inputs }, stage:'SEND', locked:false,
    }})
    expect(wrapper.text()).toContain('本次最多 8.25 米')
    await wrapper.get('input[inputmode=decimal]').setValue('8.250001')
    expect(wrapper.get('button[type=submit]').attributes()).toHaveProperty('disabled')
    await wrapper.get('input[inputmode=decimal]').setValue('8.25')
    expect(wrapper.get('button[type=submit]').attributes()).not.toHaveProperty('disabled')
  })
  it('uses the one entered delivery quantity and voucher for a counted delivery', async () => {
    const wrapper = await openDelivery()
    expect(wrapper.findAll('input[inputmode=decimal]')).toHaveLength(1)
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('save')?.[0]).toEqual(['/orders/order/actions', expect.objectContaining({
      kind:'DELIVER_AND_RECEIVE', target_id:'output', quantity:'600', received_quantity:'600', voucher:'SH-1', location_id:'bin',
    })])
  })
  it('submits actual quantity separately and catches excessive counts before posting', async () => {
    const wrapper = await openDelivery()
    await wrapper.get('input[type=checkbox]').setValue(true)
    const actual = wrapper.findAll('input[inputmode=decimal]')[1]!
    await actual.setValue('600.000001')
    expect(wrapper.get('[role=alert]').text()).toContain('超过')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('save')).toBeUndefined()
    await actual.setValue('590')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('save')?.[0]?.[1]).toMatchObject({kind:'DELIVER_AND_RECEIVE', quantity:'600', received_quantity:'590'})
  })
  it('records only the delivery when counting is deferred, even after filling a bin', async () => {
    const wrapper = await openDelivery()
    await wrapper.findAll('input[type=radio]')[1]!.setValue()
    expect(wrapper.find('[aria-label="回仓仓位"]').exists()).toBe(false)
    await wrapper.get('form').trigger('submit')
    const body = wrapper.emitted('save')?.[0]?.[1]
    expect(body).toMatchObject({kind:'DELIVER', quantity:'600', voucher:'SH-1', location_id:''})
    expect(body).not.toHaveProperty('received_quantity')
  })
})
