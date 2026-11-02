import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { reactive } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CartonSupplierAssetStatus from '../CartonSupplierAssetStatus.vue'
const api = vi.hoisted(() => ({ classifyMarkAsset: vi.fn() }))
vi.mock('@/api/cartonSupplierPortal', () => ({ cartonSupplierPortalApi: api }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))
const auth = reactive({ currentUser: { id: 'supplier', identity: { employment_epoch: 1 } }, authorizationVersion: 1, can: () => true })
const asset = { id: 'own', revision: 4, file_name: 'own.pdf', can_classify: true, workflow: { status: 'PENDING' } }
let wrapper: VueWrapper
function dialog() { return new DOMWrapper(document.querySelector<HTMLElement>('[role="dialog"]')!) }
async function open() { wrapper = mount(CartonSupplierAssetStatus, { props: { factoryId: 'huaxing', asset }, attachTo: document.body }); await wrapper.get('button').trigger('click'); await flushPromises() }
beforeEach(() => { vi.clearAllMocks(); api.classifyMarkAsset.mockResolvedValue({ id: asset.id }); auth.authorizationVersion = 1 })
afterEach(async () => { wrapper?.unmount(); await flushPromises(); document.body.innerHTML = '' })
describe('supplier-owned file status', () => {
  it('allows only draft/pending and submits the exact file revision', async () => {
    await open()
    expect(dialog().findAll('option').map(x => x.attributes('value'))).toEqual(['DRAFT', 'PENDING'])
    await dialog().get('select').setValue('DRAFT'); await dialog().trigger('submit'); await flushPromises()
    expect(api.classifyMarkAsset).toHaveBeenCalledWith('huaxing', { id: 'own', revision: 4 }, 'DRAFT', expect.any(String), expect.any(AbortSignal))
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })
  it.each([['shared', false, 'PENDING'], ['ready', true, 'READY'], ['history', true, 'HISTORY']] as const)('does not offer status writes for %s', async (_name, can_classify, status) => {
    wrapper = mount(CartonSupplierAssetStatus, { props: { factoryId: 'huaxing', asset: { ...asset, can_classify, workflow: { status } } } })
    expect(wrapper.find('button').exists()).toBe(false)
    expect(api.classifyMarkAsset).not.toHaveBeenCalled()
  })
  it('freezes unknown results and retries the same payload after closing/reopening', async () => {
    api.classifyMarkAsset.mockRejectedValueOnce(new Error('timeout')).mockResolvedValueOnce({ id: 'own' })
    await open(); await dialog().get('select').setValue('DRAFT'); await dialog().trigger('submit'); await flushPromises()
    const original = api.classifyMarkAsset.mock.calls[0]!.slice(0, 4)
    expect(dialog().get('select').attributes('disabled')).toBeDefined()
    await dialog().findAll('button').find(x => x.text() === '取消')!.trigger('click'); await flushPromises()
    await wrapper.get('button').trigger('click'); await flushPromises(); await dialog().trigger('submit'); await flushPromises()
    expect(api.classifyMarkAsset.mock.calls[1]!.slice(0, 4)).toEqual(original)
  })
  it('ignores late saves after factory or authorization context changes', async () => {
    let finish!: (value: unknown) => void
    api.classifyMarkAsset.mockImplementation(() => new Promise(resolve => { finish = resolve }))
    await open(); await dialog().trigger('submit')
    await wrapper.setProps({ factoryId: 'huakang-a' }); finish({ id: 'own' }); await flushPromises()
    expect(wrapper.emitted('changed')).toBeUndefined()
    expect(document.querySelector('[role="dialog"]')).toBeNull()
  })
})
