import { defineComponent, ref } from 'vue'
import { createPinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import CartonReceiptAllocations from '../CartonReceiptAllocations.vue'
import type { LocationAllocation } from '@/api/cartonPositions'

vi.mock('@/api/cartonPositions', () => ({ cartonPositionsApi: { create: vi.fn() } }))
const locations = [{ id: 'A', factory_id: 'huaxing', warehouse: '一仓', bin_code: '01', label: '一仓／01' },
  { id: 'B', factory_id: 'huaxing', warehouse: '二仓', bin_code: '02', label: '二仓／02' }]

describe('收料分仓分配', () => {
  it('keeps a single allocation in sync, preserves split quantities for review, and freezes saved input', async () => {
    const Host = defineComponent({
      components: { CartonReceiptAllocations },
      setup: () => ({ rows: ref<LocationAllocation[]>([]), effective: ref(10), disabled: ref(false), locations }),
      template: '<CartonReceiptAllocations v-model="rows" :effective="effective" :locations="locations" factory-id="huaxing" :disabled="disabled" />',
    })
    const wrapper = mount(Host, { global: { plugins: [createPinia()] } })
    await wrapper.get('input[aria-label="仓库及仓位"]').setValue('一仓／01')
    expect(wrapper.vm.rows).toEqual([{ location_id: 'A', quantity: 10 }])
    await wrapper.get('input[aria-label="仓库及仓位"]').setValue('不存在的仓位')
    expect(wrapper.vm.rows[0]!.location_id).toBe('')
    expect(wrapper.text()).toContain('请选择基础资料中已有的仓位')
    await wrapper.get('input[aria-label="仓库及仓位"]').setValue('一仓／01')
    wrapper.vm.effective = 12; await flushPromises()
    expect(wrapper.vm.rows[0]!.quantity).toBe(12)
    await wrapper.findAll('button').find(b => b.text() === '＋分仓存放')!.trigger('click')
    await wrapper.findAll('input[aria-label="仓库及仓位"]')[1]!.setValue('二仓／02')
    const quantities = wrapper.findAll('input[aria-label="分仓入库数量"]')
    await quantities[0]!.setValue('7'); await quantities[1]!.setValue('5')
    expect(wrapper.text()).toContain('分仓合计 12 / 有效入库 12')
    wrapper.vm.effective = 11; await flushPromises()
    expect(wrapper.vm.rows.map(r => Number(r.quantity))).toEqual([7, 5])
    expect(wrapper.get('p').classes()).toContain('text-red-600')
    await wrapper.findAll('button[aria-label="移除分仓"]')[1]!.trigger('click')
    expect(wrapper.vm.rows).toEqual([{ location_id: 'A', quantity: 11 }])
    wrapper.vm.disabled = true; await flushPromises()
    expect(wrapper.get('input[aria-label="仓库及仓位"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('button').exists()).toBe(false)
  })
})
