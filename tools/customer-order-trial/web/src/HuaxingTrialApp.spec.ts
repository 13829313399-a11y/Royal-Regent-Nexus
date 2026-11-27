import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import HuaxingTrialApp from './HuaxingTrialApp.vue'
import Workspace from '@/components/modules/sales/customer-order-center/CustomerOrderCenterWorkspace.vue'
import { customerOrderApi } from './huaxingTrialOrderApi'
const mocks = vi.hoisted(() => ({ config: vi.fn(), post: vi.fn() }))
vi.mock('./api', () => ({ api: { config: mocks.config }, http: { post: mocks.post },
  getApiErrorMessage: (e: Error) => e.message, getApiErrorMessageAsync: async (e: Error) => e.message,
  errorMessage: async (e: Error) => e.message }))
beforeEach(() => vi.clearAllMocks())
afterEach(() => vi.restoreAllMocks())
it.each(['caixing','edu','dickie','seasons'])('opens the actual workspace scoped to %s', async (code) => {
  mocks.config.mockResolvedValue({factory_id:'huaxing',customers:[{code,name:code}]})
  const wrapper=mount(HuaxingTrialApp); await flushPromises()
  expect(wrapper.getComponent(Workspace).props()).toMatchObject({localOnly:true,factoryId:'huaxing',customerCodes:[code],initialCustomerCode:code})
  expect(wrapper.find('[data-testid=customer-choice-jakks]').exists()).toBe(false)
  const file=new File(['file'],'test.xlsx');mocks.post.mockResolvedValue({data:{rows:[]},headers:{}})
  if (code === 'caixing') await customerOrderApi.previewCaixingBatch([file], file, '2026-11-19', 'huaxing')
  else if (code === 'dickie') await customerOrderApi.previewDickieBatch([file], file, '2026-11-19','huaxing')
  else await customerOrderApi.previewMappedBatch(code as 'edu', [file], file, '2026-11-19','huaxing')
  expect(mocks.post.mock.calls[0]?.[0]).toBe('/orders/preview')
  expect(mocks.post.mock.calls[0]?.[1].get('customer_code')).toBe(code)
  wrapper.unmount()
})
it('rejects mismatched factory configuration',async () => {
  mocks.config.mockResolvedValue({factory_id:'huadeng',customers:[{code:'jakks'}]})
  const wrapper=mount(HuaxingTrialApp);await flushPromises()
  expect(wrapper.findComponent(Workspace).exists()).toBe(false)
  expect(wrapper.text()).toContain('启动配置与华兴专用包不一致');wrapper.unmount()
})
