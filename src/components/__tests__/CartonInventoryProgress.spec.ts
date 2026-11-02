import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { expect, it } from 'vitest'
import Component from '../CartonInventoryProgress.vue'

it('opens inventory arrival source in receiving context with its exact request', async () => {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] })
  await router.push('/'); await router.isReady()
  const wrapper = mount(Component, { props: { balance: 3, unit: '个', formal: false, factoryId: 'huaxing', sources: [{ id: 'CSR-INVENTORY', request_no: 'SP-INVENTORY', kind: 'SAMPLE' }] }, global: { plugins: [router] } })
  expect(wrapper.get('a').attributes('href')).toContain('tab=receipts&receipt_page=supplier&special_request=CSR-INVENTORY')
  expect(wrapper.get('a').attributes('href')).toContain('factory=huaxing'); wrapper.unmount()
})
