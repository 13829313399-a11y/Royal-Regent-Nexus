import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'
import Component from '../CartonSourceLinks.vue'

describe('carton source navigation', () => {
  it('keeps factory, exact request, paper and original delivery identities in links', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] })
    await router.push('/'); await router.isReady()
    const wrapper = mount(Component, { props: { factoryId: 'huaxing', marks: true, deliveryId: 'CUD-original', sources: [{ id: 'CSR-source', request_no: 'SP-original', kind: 'SAMPLE', line_id: 'CSL-paper' }] }, global: { plugins: [router] } })
    const links = wrapper.findAll('a')
    expect(links[0]!.attributes('href')).toContain('special_request=CSR-source')
    expect(links[1]!.attributes('href')).toContain('mark_request=CSR-source&mark_line=CSL-paper')
    expect(links[2]!.attributes('href')).toContain('shipment=CUD-original')
    expect(links.every(link => link.attributes('href')?.includes('factory=huaxing'))).toBe(true)
    await wrapper.setProps({ supplier: true })
    expect(wrapper.findAll('a')).toHaveLength(1)
    expect(wrapper.get('a').attributes('href')).toContain('/carton-supplier?factory=huaxing')
    wrapper.unmount()
  })
})
