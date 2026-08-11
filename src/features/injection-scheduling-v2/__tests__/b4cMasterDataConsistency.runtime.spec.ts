import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

const routerMocks = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }))
const apiMocks = vi.hoisted(() => ({
  createMachineMaster: vi.fn(),
  createSharedMoldProposal: vi.fn(),
  getSharedMoldDetail: vi.fn(),
  listMachineMasters: vi.fn(),
  listSharedMoldCatalog: vi.fn(),
  updateMachineMaster: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: { factory: 'huakang-b' } }),
  useRouter: () => routerMocks,
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ can: () => true }) }))
vi.mock('../api/injectionSchedulingV2Api', () => apiMocks)

import MachineDatabaseView from '../MachineDatabaseView.vue'
import SharedMoldDatabaseView from '../SharedMoldDatabaseView.vue'

const mounted: VueWrapper[] = []

afterEach(() => {
  mounted.splice(0).forEach((wrapper) => wrapper.unmount())
  document.body.innerHTML = ''
  vi.clearAllMocks()
})

async function settle() {
  await flushPromises()
  await nextTick()
  await nextTick()
}

function mountPage(component: typeof SharedMoldDatabaseView | typeof MachineDatabaseView) {
  const wrapper = mount(component, {
    attachTo: document.body,
    global: { stubs: { AccountMenu: { template: '<div />' } } },
  })
  mounted.push(wrapper)
  return wrapper
}

describe('B4c master-data drawer keyboard paths', () => {
  it('focuses, traps and restores both shared-mold drawers with the selected factory copy', async () => {
    apiMocks.listSharedMoldCatalog.mockResolvedValue({
      items: [{
        id: 'mold-1', canonicalMoldNo: 'M-001', displayMoldNo: 'M-001', standardName: '测试模具',
        revision: 3, dataQuality: 'APPROVED', outputs: [], outputCount: 0, moldAClass: null,
        recommendedMachineClassRaw: '', defaultArmType: '', defaultFixtureType: '', nominalDailyCapacity: null,
        factoryCapability: null, price: null,
        factoryReadiness: { availableAssetCount: 0, status: 'NOT_FACTORY_READY' },
      }],
      page: 1, pageSize: 30, total: 1,
      summary: { totalDefinitions: 1, factoryReady: 0, notFactoryReady: 1, pendingProposals: 0, canReadPrices: false },
    })
    apiMocks.getSharedMoldDetail.mockResolvedValue({
      id: 'mold-1', canonicalMoldNo: 'M-001', displayMoldNo: 'M-001', standardName: '测试模具',
      revision: 3, dataQuality: 'APPROVED', aliases: [], outputs: [], moldAClass: null,
      recommendedMachineClassRaw: '', capabilities: [], assets: [], prices: [], priceAccess: 'RESTRICTED',
      factoryReadiness: { availableAssetCount: 0, status: 'NOT_FACTORY_READY' },
    })

    const wrapper = mountPage(SharedMoldDatabaseView)
    await settle()

    const detailOpener = wrapper.get('.row-detail-button')
    ;(detailOpener.element as HTMLElement).focus()
    await detailOpener.trigger('click')
    await settle()
    const detailDialog = wrapper.get('[role="dialog"][aria-labelledby="shared-mold-detail-title"]')
    const detailClose = detailDialog.get('button[aria-label="关闭模具详情"]')
    expect(document.activeElement).toBe(detailClose.element)
    detailClose.element.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }))
    await settle()
    expect(wrapper.find('[aria-labelledby="shared-mold-detail-title"]').exists()).toBe(false)
    expect(document.activeElement).toBe(detailOpener.element)

    const proposalOpener = wrapper.get('.command-button.auto')
    ;(proposalOpener.element as HTMLElement).focus()
    await proposalOpener.trigger('click')
    await settle()
    const proposalDialog = wrapper.get('[role="dialog"][aria-labelledby="shared-mold-proposal-title"]')
    expect(proposalDialog.text()).toContain('华康 B机安能力')
    const proposalClose = proposalDialog.get('button[aria-label="关闭模具提案"]')
    expect(document.activeElement).toBe(proposalClose.element)
    proposalClose.element.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }))
    await settle()
    expect(document.activeElement).toBe(proposalOpener.element)
  })

  it('gives the machine editor dialog focus, Escape and opener recovery', async () => {
    apiMocks.listMachineMasters.mockResolvedValue([])
    const wrapper = mountPage(MachineDatabaseView)
    await settle()

    const opener = wrapper.get('.command-button.auto')
    ;(opener.element as HTMLElement).focus()
    await opener.trigger('click')
    await settle()
    const dialog = wrapper.get('[role="dialog"][aria-labelledby="machine-editor-title"]')
    expect(dialog.text()).toContain('华康 B')
    const close = dialog.get('button[aria-label="关闭机台资料编辑"]')
    expect(document.activeElement).toBe(close.element)
    close.element.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }))
    await settle()
    expect(wrapper.find('[aria-labelledby="machine-editor-title"]').exists()).toBe(false)
    expect(document.activeElement).toBe(opener.element)
  })
})
