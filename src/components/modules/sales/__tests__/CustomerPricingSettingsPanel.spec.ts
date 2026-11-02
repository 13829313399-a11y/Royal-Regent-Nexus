import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/auth'
import { customerPricingSettingsApi } from '@/api/customerPricingSettings'
import type { AuthMeResponse, AuthzMode } from '@/api/auth'
import CustomerPricingSettingsPanel from '../CustomerPricingSettingsPanel.vue'
import type { CustomerPricingSettings } from '@/lib/customerPriceConverters/pricingSettings'
vi.mock('@/api/customerPricingSettings', () => ({ customerPricingSettingsApi: { get: vi.fn(), save: vi.fn() } }))
const read = 'customer_price:settings_read', manage = 'customer_price:settings_manage'
function session(department = 'sales-business', permissions = [read], mode: AuthzMode = 'enforce'): AuthMeResponse {
  return { id: 's1', username: 'sales', display_name: '业务', roles: ['业务'], permissions, factory_scopes: ['huaxing'], department_scopes: [department], profile: { primary_factory_id: 'huaxing', primary_department: department, position: '', confirmation_status: 'confirmed' }, grants: [{ role_id: 'sales', role_name: '业务', factory_id: 'huaxing', department: 'sales-business', permissions, data_scope: 'department' }], effective_access: permissions.map(permission_code => ({ permission_code, factory_id: 'huaxing', department: 'sales-business', effect: 'allow', allowed: true, source_type: 'role', source_ids: [] })), authz_mode: mode, force_password_change: false }
}
function settings(customer_id = 'buzzbee'): CustomerPricingSettings {
  return { factory_id: 'huaxing', customer_id, revision: 1, materials: [{ material: 'Private resin', price: 16.7, currency: 'HKD', unit: 'kg' }], rates: { detail_multiplier: 1.05 }, texts: {}, rate_definitions: { detail_multiplier: { label: '明细倍率', kind: 'multiplier' } }, updated_at: '', updated_by_name: '' }
}
function panel() { return mount(CustomerPricingSettingsPanel, { props: { factoryId: 'huaxing', customerId: 'buzzbee', customerName: 'BuzzBee', customers: [{ id: 'buzzbee', name: 'BuzzBee' }, { id: 'yinhui', name: '银辉' }] } }) }
describe('private customer pricing maintenance', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.resetAllMocks(); vi.mocked(customerPricingSettingsApi.get).mockResolvedValue(settings()) })
  it.each(['legacy','shadow','enforce'] as const)('hides nonbusiness and explicitly denied users in %s mode', async mode => {
    const auth = useAuthStore(); auth.applySession(session('engineering', [read, manage], mode))
    const wrapper = panel(); expect(wrapper.find('section').exists()).toBe(false)
    const user = session('sales-business',[read,manage],mode)
    user.effective_access![0] = { ...user.effective_access![0]!, effect: 'deny', allowed: false, source_type: 'override' }
    auth.applySession(user); await flushPromises()
    expect(wrapper.find('section').exists()).toBe(false); expect(customerPricingSettingsApi.get).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('allows read-only staff and only saves for authorized maintainers', async () => {
    const auth = useAuthStore(); auth.applySession(session())
    const wrapper = panel(); await wrapper.get('button').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('当前为只读权限')
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    auth.applySession(session('sales-business', [read, manage])); await flushPromises()
    await wrapper.get('[aria-label="明细倍率"]').setValue(1.2)
    vi.mocked(customerPricingSettingsApi.save).mockImplementation(async value => ({ ...value, revision: 2 }))
    await wrapper.findAll('button').find(b => b.text() === '保存基础信息')!.trigger('click'); await flushPromises()
    expect(customerPricingSettingsApi.save).toHaveBeenCalledWith(expect.objectContaining({ factory_id: 'huaxing', customer_id: 'buzzbee', revision: 1, rates: { detail_multiplier: 1.2 } }))
    expect(wrapper.text()).toContain('下一次转换使用新参数')
    wrapper.unmount()
  })
  it('discards delayed values after customer switches or permission loss', async () => {
    const auth = useAuthStore(); auth.applySession(session())
    let complete!: (v: CustomerPricingSettings) => void
    vi.mocked(customerPricingSettingsApi.get).mockImplementationOnce(() => new Promise(resolve => { complete = resolve }))
    const wrapper = panel(); await wrapper.get('button').trigger('click')
    vi.mocked(customerPricingSettingsApi.get).mockResolvedValue({ ...settings('yinhui'), materials: [] })
    await wrapper.setProps({ customerId: 'yinhui', customerName: '银辉' }); await flushPromises()
    complete(settings()); await flushPromises()
    expect(wrapper.find('[aria-label="料型 1"]').exists()).toBe(false)
    auth.applySession(session('engineering')); await flushPromises()
    expect(wrapper.find('section').exists()).toBe(false)
    wrapper.unmount()
  })
  it('keeps cross-factory read access local and honors admin explicit deny', () => {
    const auth = useAuthStore(), user = session()
    user.grants![0] = { ...user.grants![0]!, unrestricted_department: true, scope_mode: 'cross_factory_read', read_permission_codes: [read] }
    auth.applySession(user)
    expect(auth.can(read,'huaxing','sales-business')).toBe(true)
    expect(auth.can(read,'huakang-a','sales-business')).toBe(false)
    user.grants = [{ role_id: 'admin', role_code: 'admin', role_name: 'admin', factory_id: '*', department: '*', permissions: [read], data_scope: 'all' }]
    user.effective_access![0] = { ...user.effective_access![0]!, effect: 'deny', allowed: false, source_type: 'override' }
    auth.applySession(user)
    expect(auth.can(read,'huaxing','sales-business')).toBe(false)
  })
  it('lets a Huaxing 360 follower maintain material prices and allocations only', async () => {
    const auth = useAuthStore()
    auth.applySession(session('sales-business', [read, 'customer_price:import_internal_quote']))
    const data: CustomerPricingSettings = {
      ...settings('three-sixty-huaxing'),
      materials: [{ material: 'PP', price: 1.55, currency: 'USD', unit: 'kg' }],
      rates: { hkd_usd: 7.8, testing_allocation_qty: 100000 },
      rate_definitions: { hkd_usd: { label: '港元兑美元', kind: 'exchange' }, testing_allocation_qty: { label: '测试费摊分数量', kind: 'price' } },
      texts: { comments: 'Existing terms' }, text_definitions: { comments: { label: '报客说明' } },
    }
    vi.mocked(customerPricingSettingsApi.get).mockResolvedValue(data)
    const wrapper = panel()
    await wrapper.setProps({ customerId: 'three-sixty-huaxing', customerName: '360（华兴临时）' })
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(wrapper.get('fieldset').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('[aria-label="港元兑美元"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[aria-label="报客说明"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[aria-label="料价 1"]').setValue(1.6)
    await wrapper.get('[aria-label="测试费摊分数量"]').setValue(120000)
    await wrapper.findAll('button').find(b => b.text() === '新增料型')!.trigger('click')
    await wrapper.get('[aria-label="料型 2"]').setValue('New resin')
    await wrapper.get('[aria-label="料价 2"]').setValue(3)
    vi.mocked(customerPricingSettingsApi.save).mockImplementation(async value => ({ ...value, revision: 2 }))
    await wrapper.findAll('button').find(b => b.text() === '保存基础信息')!.trigger('click'); await flushPromises()
    expect(customerPricingSettingsApi.save).toHaveBeenCalledWith(expect.objectContaining({
      customer_id: 'three-sixty-huaxing', rates: { hkd_usd: 7.8, testing_allocation_qty: 120000 },
      texts: { comments: 'Existing terms' }, materials: [
        { material: 'PP', price: 1.6, currency: 'USD', unit: 'kg' },
        { material: 'New resin', price: 3, currency: 'USD', unit: 'kg' },
      ],
    }))
    vi.mocked(customerPricingSettingsApi.get).mockResolvedValue(settings('buzzbee'))
    await wrapper.setProps({ customerId: 'buzzbee' }); await flushPromises()
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
  it.each(['legacy', 'shadow', 'enforce'] as const)('honors explicit maintenance denies for 360 followers in %s mode', async mode => {
    const user = session('sales-business', [read, 'customer_price:import_internal_quote'], mode)
    user.effective_access!.push({ permission_code: manage, factory_id: 'huaxing', department: 'sales-business', effect: 'deny', allowed: false, source_type: 'user_override', source_ids: ['deny'] })
    useAuthStore().applySession(user)
    vi.mocked(customerPricingSettingsApi.get).mockResolvedValue(settings('three-sixty-huaxing'))
    const wrapper = panel()
    await wrapper.setProps({ customerId: 'three-sixty-huaxing' })
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('当前为只读权限')
    wrapper.unmount()
  })
})
