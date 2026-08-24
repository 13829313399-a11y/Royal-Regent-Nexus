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
      recommendedMachineClassRaw: '',
      capabilities: [
        { id: 'cap-1', machineClass: 14, requiredArmType: 'single', requiredFixtureType: 'suction_cup', nominalDailyCapacity: 3200, priority: 20, revision: 2 },
        { id: 'cap-2', machineClass: 7, requiredArmType: 'manual', requiredFixtureType: 'manual', nominalDailyCapacity: 1800, priority: 10, revision: 1 },
      ],
      assets: [
        { id: 'asset-1', assetCode: 'M-001-A', serialNo: 'SN-001', currentLocation: 'A 区', status: 'AVAILABLE', actualCavityCount: 2, revision: 2 },
        { id: 'asset-2', assetCode: 'M-001-B', serialNo: '', currentLocation: '维修区', status: 'MAINTENANCE', actualCavityCount: null, revision: 1 },
      ],
      prices: [], priceAccess: 'RESTRICTED',
      factoryReadiness: { availableAssetCount: 2, status: 'FACTORY_READY' },
    })

    const wrapper = mountPage(SharedMoldDatabaseView)
    await settle()

    const commandContext = wrapper.get('[data-command-zone="context"]')
    const commandSearch = wrapper.get('[data-command-zone="search"]')
    const commandActions = wrapper.get('[data-command-zone="actions"]')
    expect(commandContext.get('select[aria-label="厂区"]').element).toBeTruthy()
    expect(commandSearch.get('input[aria-label="搜索共享模具"]').attributes('type')).toBe('search')
    expect(commandActions.text()).toContain('返回排产')
    expect(commandActions.text()).toContain('厂区机台库')
    expect(commandActions.text()).toContain('刷新数据')
    expect(commandActions.text()).toContain('新增模具提案')

    const detailOpener = wrapper.get('.row-detail-button')
    ;(detailOpener.element as HTMLElement).focus()
    await detailOpener.trigger('click')
    await settle()
    const detailDialog = wrapper.get('[role="dialog"][aria-labelledby="shared-mold-detail-title"]')
    const detailClose = detailDialog.get('button[aria-label="关闭模具详情"]')
    expect(detailDialog.text()).toContain('机安能力明细2 项')
    expect(detailDialog.text()).toContain('14A单臂 · 吸盘计划目标：3,200 啤 / 日')
    expect(detailDialog.text()).toContain('7A半自动 · 人工取件计划目标：1,800 啤 / 日')
    expect(detailDialog.text()).toContain('实体模具明细2 个')
    expect(detailDialog.text()).toContain('M-001-A可排机A 区 · 2 穴 · 序列号 SN-001')
    expect(detailDialog.text()).toContain('M-001-B维护中维修区 · 穴数待补充')
    expect(detailDialog.text()).toContain('可用实体1共 2 个实体记录')
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

    const commandContext = wrapper.get('[data-command-zone="context"]')
    const commandSearch = wrapper.get('[data-command-zone="search"]')
    const commandActions = wrapper.get('[data-command-zone="actions"]')
    expect(commandContext.get('select[aria-label="厂区"]').element).toBeTruthy()
    expect(commandSearch.get('input[aria-label="搜索厂区机台"]').attributes('type')).toBe('search')
    expect(commandActions.text()).toContain('返回排产')
    expect(commandActions.text()).toContain('共享模具库')
    expect(commandActions.text()).toContain('刷新数据')
    expect(commandActions.text()).toContain('新增机台')

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
