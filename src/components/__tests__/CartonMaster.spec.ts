import { mount, flushPromises } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import Assist from '../CartonMasterOrderAssist.vue'
import Lookup from '../CartonMasterLookup.vue'
import Workspace from '../CartonMasterWorkspace.vue'
import Settings from '../CartonMasterSettings.vue'
import { cartonMasterApi, defaultMasterData, emptyMaster, masterDueRules, historicalNumberSamples, numberWarning, type MasterRecord } from '@/api/cartonMaster'

vi.mock('@/lib/http', () => ({ http: { get: vi.fn(), post: vi.fn(), patch: vi.fn() }, getApiErrorMessage: () => '请求失败' }))
const record = (id: string, customer = '360', count = '120'): MasterRecord => ({
  id, kind: 'CONFIG', customer_code: customer, code: '00123', status: 'ACTIVE', revision: 1,
  preferred: false, maintained: false, updated_at: '', sources: [],
  data: { ...defaultMasterData(), product_name: '消防车', lines: [
    { packaging_type: '外箱', paper_quality: 'A33', specification: '30*20*15', dimension_unit: 'cm', unit: '个', usage_quantity: count },
    { packaging_type: '滑板纸', paper_quality: 'A33', specification: '30*20', dimension_unit: 'cm', unit: '张', usage_quantity: count },
  ] },
})

describe('纸箱基础资料', () => {
  it('keeps full alternative paper sets, shares configurations across customers and leaves differences as reminders', async () => {
    const a = record('A'), b = record('B', '360', '100'), foreign = record('F', 'OTHER')
    const wrapper = mount(Assist, { props: { records: [a, b, foreign, { ...a, id: 'STOP', status: 'INACTIVE' }], customer: '360', item: '00123', contract: 'C1', product: '消防车', lines: a.data.lines! } })
    expect(wrapper.findAll('button')).toHaveLength(3)
    expect(wrapper.text()).toContain('3 套历史配置')
    expect(wrapper.text()).toContain('滑板纸')
    await wrapper.findAll('button')[1]!.trigger('click')
    expect(wrapper.emitted('select')![0]![0]).toEqual(b)
    await wrapper.setProps({ lines: b.data.lines!.map(l => ({ ...l, unit: '片' })) })
    expect(wrapper.text()).toContain('本次包装与已有配置不同')
    expect(wrapper.text()).toContain('核对无误可保留')
    expect(wrapper.findAll('button').every(b => b.attributes('disabled') === undefined)).toBe(true)
  })

  it('allows customer-specific override and explicit suppression of the factory date suggestion', () => {
    const factory: MasterRecord = { ...record('FACTORY', ''), kind: 'RULE', code: '', data: { lead_days: 5, customer_days: 10 } }
    const customer: MasterRecord = { ...record('CUSTOMER'), kind: 'RULE', code: '', data: { lead_days: 2, customer_days_disabled: true } }
    expect(masterDueRules([factory, customer], '360')).toMatchObject({ lead_days: 2, customer_days: null })
    expect(masterDueRules([factory, customer], 'OTHER')).toMatchObject({ lead_days: 5, customer_days: 10 })
  })

  it('renders ordinary users read-only and allows authorized maintenance without mutating loaded history', async () => {
    const a = record('A')
    const get = vi.spyOn(cartonMasterApi, 'get').mockResolvedValue({ ...emptyMaster(), records: [a] })
    const wrapper = mount(Workspace, { props: { factoryId: 'huaxing', customers: [{ id: 'C', customer_code: '360', customer_name: '360', status: 'ACTIVE' } as any] } })
    await flushPromises()
    await wrapper.get('[role="tab"][aria-selected="false"]').trigger('click')
    expect(wrapper.find('[aria-label="修改基础资料 00123"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('用于落单')
    get.mockResolvedValue({ ...emptyMaster(), can_manage: true, records: [a] })
    await wrapper.findAll('button').find(b => b.text() === '刷新资料')!.trigger('click'); await flushPromises()
    await wrapper.get('[aria-label="修改基础资料 00123"]').trigger('click')
    expect(wrapper.get<HTMLInputElement>('[aria-label="基础资料修改原因"]').element.value).toBe('修正基础资料')
    await wrapper.get('[aria-label="基础资料产品名称"]').setValue('修改后的物品名')
    expect(a.data.product_name).toBe('消防车')
    expect(wrapper.findAll('[aria-label="资料装箱数"]')).toHaveLength(2)
    expect(wrapper.get('[aria-label="资料编号名称"]').attributes('disabled')).toBeDefined()
    wrapper.unmount(); get.mockRestore()
  })
})

it('uses saved templates without re-learning from later history or another customer', () => {
  const a: MasterRecord = { ...record('A'), kind: 'CONTRACT', sources: [{ order_no: 'O1', order_date: '', contract_no: 'SC700149169/600', item_no: '203300001', configuration: {} }] }
  const rule: MasterRecord = { ...record('RULE'), kind: 'RULE', data: { ...defaultMasterData(), contract_rule: { ...defaultMasterData().contract_rule, templates: ['SC{9}/{3,4}'], frozen: true } } }
  const foreign = { ...a, id: 'FOREIGN', customer_code: 'OTHER', sources: [{ ...a.sources[0]!, contract_no: 'WRONG' }] }
  expect(historicalNumberSamples([a, a, foreign], '360', 'contract_rule')).toEqual(['SC700149169/600'])
  expect(numberWarning(masterDueRules([a, rule], '360').contract_rule, 'SC700143393/1600')).toBe(false)
  const later = { ...a, sources: [{ ...a.sources[0]!, contract_no: 'SC700149169/60000' }] }
  expect(numberWarning(masterDueRules([later, rule], '360').contract_rule, 'SC700149169/60000')).toBe(true)
  expect(numberWarning(masterDueRules([a, rule], 'OTHER').contract_rule, 'ANY')).toBe(false)
  expect(numberWarning(masterDueRules([a], '360').contract_rule, 'ANY')).toBe(false)
})

it('keeps authorization and hard-check reasons explicit while routine maintenance is prefilled', async () => {
  const get = vi.spyOn(cartonMasterApi, 'get').mockResolvedValue({ ...emptyMaster(), can_manage: true })
  const wrapper = mount(Workspace, { props: { factoryId: 'huaxing', customers: [{ id: 'C', customer_code: '360', customer_name: '360' } as any] } })
  await flushPromises()
  const click = async (label: string) => { await wrapper.findAll('button').find(b => b.text() === label)!.trigger('click') }
  await wrapper.get('[aria-label="设置客户规则 360"]').trigger('click')
  expect(wrapper.text()).toContain('尚未识别到格式')
  expect(wrapper.get<HTMLInputElement>('[aria-label="基础资料修改原因"]').element.value).toBe('新增基础资料')
  await wrapper.get('[aria-label="合同号格式检查方式"]').setValue('BLOCK')
  expect(wrapper.get<HTMLInputElement>('[aria-label="基础资料修改原因"]').element.value).toBe('')
  await wrapper.get('[aria-label="关闭基础资料编辑"]').trigger('click')
  expect(wrapper.find('[aria-label="仓库维护权限设置"]').exists()).toBe(false)
  expect(wrapper.text()).not.toContain('新增仓库维护授权')
  wrapper.unmount(); get.mockRestore()
})

it.each(['AUTO', 'OFF'])('requires an explanation when disabling an existing hard check to %s', async mode => {
  const data = defaultMasterData(); data.contract_rule.mode = 'BLOCK'
  const rule: MasterRecord = { ...record('RULE'), kind: 'RULE', code: '', data }
  const get = vi.spyOn(cartonMasterApi, 'get').mockResolvedValue({ ...emptyMaster(), can_manage: true, records: [rule] })
  const wrapper = mount(Workspace, { props: { factoryId: 'huaxing', customers: [{ id: 'C', customer_code: '360', customer_name: '360', status: 'ACTIVE' } as any] } })
  await flushPromises()
  await wrapper.get('[aria-label="设置客户规则 360"]').trigger('click')
  await wrapper.get('[aria-label="合同号格式检查方式"]').setValue(mode)
  expect(wrapper.get<HTMLInputElement>('[aria-label="基础资料修改原因"]').element.value).toBe('')
  wrapper.unmount(); get.mockRestore()
})

it('prefers pasted examples, preserves manual edits and keeps reopened formats frozen', async () => {
  const history: MasterRecord = { ...record('H'), kind: 'CONTRACT', sources: [{ order_no: 'O1', order_date: '', contract_no: 'OLD00001', item_no: '203307004', configuration: {} }] }
  const get = vi.spyOn(cartonMasterApi, 'get').mockResolvedValue({ ...emptyMaster(), can_manage: true, records: [history] })
  const save = vi.spyOn(cartonMasterApi, 'save').mockResolvedValue(record('S'))
  const wrapper = mount(Workspace, { props: { factoryId: 'huaxing', customers: [{ id: 'C', customer_code: '360', customer_name: '360' } as any] } })
  await flushPromises()
  const click = async (label: string) => { await wrapper.findAll('button').find(b => b.text() === label)!.trigger('click') }
  await wrapper.get('[aria-label="设置客户规则 360"]').trigger('click')
  expect(wrapper.get<HTMLTextAreaElement>('[aria-label="合同号固定格式"]').element.value).toBe('OLD{5}')
  await wrapper.get('[aria-label="合同号识别样例"]').setValue('SC700149169/600\nSC700143393/1600')
  await wrapper.get('[aria-label="识别合同号格式"]').trigger('click')
  expect(wrapper.get<HTMLTextAreaElement>('[aria-label="合同号固定格式"]').element.value).toBe('SC{9}/{3,4}')
  expect(wrapper.text()).toContain('SC＋9 位数字＋/＋3 或 4 位数字')
  await wrapper.get('[aria-label="合同号固定格式"]').setValue('SC{9}/{3,4,5}')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  const saved = save.mock.calls[0]![1]
  expect(saved.data.contract_rule).toMatchObject({ templates: ['SC{9}/{3,4,5}'], frozen: true, source: 'MANUAL', sample_count: 2 })
  const row: MasterRecord = { ...record('S'), ...saved, revision: 1 }
  get.mockResolvedValue({ ...emptyMaster(), can_manage: true, records: [history, row] })
  await click('刷新资料'); await flushPromises()
  await wrapper.get('[aria-label="设置客户规则 360"]').trigger('click')
  expect(wrapper.get<HTMLTextAreaElement>('[aria-label="合同号固定格式"]').element.value).toBe('SC{9}/{3,4,5}')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(save.mock.calls[1]![1].data.contract_rule.templates).toEqual(['SC{9}/{3,4,5}'])
  wrapper.unmount(); get.mockRestore(); save.mockRestore()
})

it('keeps two pages and edits the one existing factory default in its fixed scope', async () => {
  const factory: MasterRecord = { ...record('FACTORY', ''), kind: 'RULE', code: '', data: { ...defaultMasterData(), lead_days: 8 } }
  const get = vi.spyOn(cartonMasterApi, 'get').mockResolvedValue({ ...emptyMaster(), can_manage: true, records: [factory] })
  const save = vi.spyOn(cartonMasterApi, 'save').mockResolvedValue(factory)
  const wrapper = mount(Workspace, { props: { factoryId: 'huaxing', customers: [] } })
  await flushPromises()
  expect(wrapper.findAll('[role="tab"]').map(t => t.text())).toEqual(['基础设置', '货号与包装'])
  expect(wrapper.findAll('button').some(b => b.text() === '维护客户资料')).toBe(false)
  await wrapper.findAll('button').find(b => b.text() === '设置通用交期')!.trigger('click')
  expect(wrapper.get('[aria-label="资料所属客户"]').attributes('disabled')).toBeDefined()
  expect(wrapper.find('[aria-label="合同号格式检查方式"]').exists()).toBe(false)
  await wrapper.get('[aria-label="默认采购提前天数"]').setValue('6')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(save).toHaveBeenCalledWith('huaxing', expect.objectContaining({ customer_code: '', expected_revision: 1, data: expect.objectContaining({ lead_days: 6 }) }), 'FACTORY')
  wrapper.unmount(); save.mockRestore(); get.mockRestore()
})

it('shows customers without rules, inherited dates, contracts and only authorized location controls', async () => {
  const factory: MasterRecord = { ...record('FACTORY', ''), kind: 'RULE', code: '', data: { lead_days: 7, customer_days: 15 } }
  const contract: MasterRecord = { ...record('CT'), kind: 'CONTRACT', code: 'SC123', data: { item_nos: ['123456'] } }
  const locations = [{ id: 'P1', warehouse: 'A', bin_code: '01', status: 'ACTIVE' }, { id: 'P2', warehouse: 'B', bin_code: '02', status: 'INACTIVE' }] as any
  const wrapper = mount(Settings, { props: { workspace: { ...emptyMaster(), records: [factory, contract], locations, warehouses: ['A'] }, customers: [{ id: 'C', customer_code: '360', customer_name: '360', status: 'ACTIVE' } as any] } })
  expect(wrapper.text()).toContain('提前 7 天')
  expect(wrapper.text()).toContain('建议下单后 15 天')
  expect(wrapper.find('[aria-label="编辑客户 360"]').exists()).toBe(false)
  expect(wrapper.find('[aria-label="仓库维护权限设置"]').exists()).toBe(false)
  expect(wrapper.get('[aria-label="修改仓位 A 01"]').attributes('disabled')).toBeUndefined()
  expect(wrapper.get('[aria-label="修改仓位 B 02"]').attributes('disabled')).toBeDefined()
  await wrapper.get('[aria-label="修改仓位 A 01"]').trigger('click')
  expect(wrapper.emitted('location')![0]![0]).toEqual(locations[0])
  await wrapper.get('[aria-label="查找客户与合同"]').setValue('SC123')
  expect(wrapper.text()).toContain('360')
  await wrapper.get('[aria-label="查找客户与合同"]').setValue('不存在')
  expect(wrapper.text()).toContain('没有符合条件的客户')
  wrapper.unmount()
})


it('opens only matching contracts and filters packaging by active status', async () => {
  const customers = [{ id: 'C', customer_code: '360', customer_name: '360', status: 'ACTIVE' }] as any
  const c1 = { ...record('C1'), kind: 'CONTRACT', code: 'SC-HIT', data: { item_nos: ['HIT-ITEM'] } } as MasterRecord
  const c2 = { ...c1, id: 'C2', code: 'SC-OTHER', data: { item_nos: ['OTHER-ITEM'] } }
  const settings = mount(Settings, { props: { customers, workspace: { ...emptyMaster(), records: [c1, c2] } } })
  await settings.get('[aria-label="查找客户与合同"]').setValue('HIT-ITEM')
  expect(settings.get('details').attributes('open')).toBeDefined()
  expect(settings.text()).toContain('SC-HIT')
  expect(settings.text()).not.toContain('SC-OTHER')
  settings.unmount()
  vi.spyOn(cartonMasterApi, 'get').mockResolvedValue({ ...emptyMaster(), records: [{ ...record('ON'), code: 'ACTIVE-ITEM' }, { ...record('OFF'), code: 'STOPPED-ITEM', status: 'INACTIVE' }] })
  const wrapper = mount(Workspace, { props: { factoryId: 'huaxing', customers, initialTab: 'CONFIG' } })
  await flushPromises()
  await wrapper.get('[aria-label="货号资料状态"]').setValue('INACTIVE')
  expect(wrapper.get('table').text()).toContain('STOPPED-ITEM')
  expect(wrapper.get('table').text()).not.toContain('ACTIVE-ITEM')
  wrapper.unmount()
})


it('separates warehouse creation, group rename and scoped bin creation', async () => {
  const locations = [{ id: 'P1', factory_id: 'huaxing', warehouse: 'A', bin_code: '01', label: 'A/01', revision: 3 }]
  vi.spyOn(cartonMasterApi, 'get').mockResolvedValue({ ...emptyMaster(), can_manage: true, locations })
  const createWarehouse = vi.spyOn(cartonMasterApi, 'createWarehouse').mockResolvedValue(locations)
  const renameWarehouse = vi.spyOn(cartonMasterApi, 'renameWarehouse').mockResolvedValue(locations)
  const wrapper = mount(Workspace, { props: { factoryId: 'huaxing', customers: [] } })
  await flushPromises()
  await wrapper.findAll('button').find(b => b.text() === '添加仓库')!.trigger('click')
  expect(wrapper.find('[aria-label="首个仓位"]').exists()).toBe(true)
  await wrapper.get('[aria-label="仓库名称"]').setValue('B')
  await wrapper.get('[aria-label="首个仓位"]').setValue('B01')
  await wrapper.get('form[aria-label="维护仓库"]').trigger('submit'); await flushPromises()
  expect(createWarehouse).toHaveBeenCalledWith('huaxing', 'B', 'B01', '添加仓库资料')
  await wrapper.get('[aria-label="添加 A 仓位"]').trigger('click')
  expect(wrapper.get<HTMLInputElement>('[aria-label="维护仓库名称"]').element.value).toBe('A')
  expect(wrapper.get('[aria-label="维护仓库名称"]').attributes('readonly')).toBeDefined()
  await wrapper.get('form[aria-label="维护仓位"]').findAll('button').find(b => b.text() === '关闭')!.trigger('click')
  await wrapper.get('[aria-label="修改仓库 A"]').trigger('click')
  expect(wrapper.find('[aria-label="首个仓位"]').exists()).toBe(false)
  await wrapper.get('[aria-label="仓库名称"]').setValue('A-NEW')
  await wrapper.get('form[aria-label="维护仓库"]').trigger('submit'); await flushPromises()
  expect(renameWarehouse).toHaveBeenCalledWith('huaxing', 'A', 'A-NEW', { P1: 3 }, '修改仓库名称')
  wrapper.unmount()
})


it('suggests complete configurations by partial name across customers while excluding inactive records', async () => {
  const a = record('A'), variant = record('B', '360', '60')
  const foreign = record('OTHER', 'OTHER'), stopped = { ...record('STOP'), status: 'INACTIVE' as const }
  const wrapper = mount(Lookup, { props: { records: [a, variant, foreign, stopped], customer: '360', query: '消防', field: 'product' }, slots: { default: '<input aria-label="查找" />' } })
  await wrapper.get('input').trigger('focusin')
  expect(wrapper.findAll('button')).toHaveLength(3)
  expect(wrapper.emitted('select')).toBeUndefined()
  await wrapper.findAll('button')[1]!.trigger('click')
  expect(wrapper.emitted('select')?.[0]).toEqual([variant])
  expect(wrapper.findAll('button')).toHaveLength(0)
  await wrapper.setProps({ query: '无此产品' })
  await wrapper.get('input').trigger('input')
  expect(wrapper.text()).toContain('可继续手动填写')
  wrapper.unmount()
})

it('matches partial normalized contract numbers and emits only the selected contract', async () => {
  const a = { ...record('C'), kind: 'CONTRACT' as const, code: 'SC700149169/600', data: { ...defaultMasterData(), item_nos: ['00123'] } }
  const wrapper = mount(Lookup, { props: { records: [a], customer: '360', query: 'sc 700149', field: 'contract' }, slots: { default: '<input />' } })
  await wrapper.get('input').trigger('focusin')
  expect(wrapper.text()).toContain('00123')
  await wrapper.get('button').trigger('click')
  expect(wrapper.emitted('select')?.[0]).toEqual([a])
  await wrapper.setProps({ disabled: true })
  await wrapper.get('input').trigger('focusin')
  expect(wrapper.findAll('button')).toHaveLength(0)
  wrapper.unmount()
})

 it('edits visible paper options separately and suppresses replaced history while preserving factory rules', async () => {
    const config = record('PAPER')
    const rule = { ...record('FACTORY', ''), kind: 'RULE', code: '', data: { ...defaultMasterData(), lead_days: 8, contract_rule: { ...defaultMasterData().contract_rule, mode: 'WARN' } } } as MasterRecord
    vi.spyOn(cartonMasterApi, 'get').mockResolvedValue({ ...emptyMaster(), can_manage: true, records: [config, rule], paper_history: { paper_quality: ['B3B'] } })
    const save = vi.spyOn(cartonMasterApi, 'save').mockResolvedValue(rule)
    const wrapper = mount(Workspace, { props: { factoryId: 'huaxing', customers: [] } })
    await flushPromises()
    await wrapper.findAll('button').find(b => b.text() === '添加 / 修改纸品选项')!.trigger('click')
    expect(wrapper.find('[aria-label="默认采购提前天数"]').exists()).toBe(false)
    expect(wrapper.get<HTMLTextAreaElement>('[aria-label="基础纸质选项"]').element.value.split('\n')).toEqual(['B3B', 'A33'])
    await wrapper.get('[aria-label="基础纸质选项"]').setValue('B3B\nA35')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(save).toHaveBeenLastCalledWith('huaxing', expect.objectContaining({ expected_revision: 1, data: expect.objectContaining({ lead_days: 8, contract_rule: rule.data.contract_rule, paper_qualities: ['B3B', 'A35'], hidden_paper_qualities: ['A33'] }) }), 'FACTORY')
    expect(config.data.lines[0]!.paper_quality).toBe('A33')
    wrapper.unmount()
  })


it('requires explicit warehouse deletion confirmation, preserves refusal and sends the complete warehouse revision set', async () => {
  const locations = [
    { id: 'P1', factory_id: 'huaxing', warehouse: 'A', bin_code: '01', label: 'A/01', revision: 3 },
    { id: 'P2', factory_id: 'huaxing', warehouse: 'A', bin_code: '02', label: 'A/02', revision: 5 },
  ]
  const get = vi.spyOn(cartonMasterApi, 'get').mockResolvedValue({ ...emptyMaster(), can_manage: true, locations })
  const remove = vi.spyOn(cartonMasterApi, 'deleteWarehouse').mockRejectedValueOnce(new Error('used')).mockResolvedValue({ deleted: true })
  const wrapper = mount(Workspace, { props: { factoryId: 'huaxing', customers: [] } })
  await flushPromises()
  await wrapper.get('[aria-label="修改仓库 A"]').trigger('click')
  await wrapper.findAll('button').find(b => b.text() === '删除仓库')!.trigger('click')
  expect(remove).not.toHaveBeenCalled()
  expect(wrapper.text()).toContain('全部 2 个仓位')
  expect(wrapper.text()).toContain('有库存、收料、出入库、调仓或盘点记录')
  await wrapper.get('form[aria-label="维护仓库"]').trigger('submit'); await flushPromises()
  expect(remove).toHaveBeenCalledWith('huaxing', 'A', { P1: 3, P2: 5 }, '删除未使用空仓')
  expect(wrapper.find('form[aria-label="维护仓库"]').exists()).toBe(true)
  expect(wrapper.find('[role="alert"]').text()).toBe('请求失败')
  get.mockResolvedValue({ ...emptyMaster(), can_manage: true, locations: [] })
  await wrapper.get('form[aria-label="维护仓库"]').trigger('submit'); await flushPromises()
  expect(wrapper.find('form[aria-label="维护仓库"]').exists()).toBe(false)
  expect(wrapper.find('[aria-label="修改仓库 A"]').exists()).toBe(false)
  expect(wrapper.emitted('changed')).toHaveLength(1)
  wrapper.unmount(); vi.restoreAllMocks()
})

it('does not expose whole-warehouse deletion to a warehouse-only maintainer or retain it after factory changes', async () => {
  const locations = [{ id: 'P1', factory_id: 'huaxing', warehouse: 'A', bin_code: '01', label: 'A/01', revision: 3 }]
  const get = vi.spyOn(cartonMasterApi, 'get').mockResolvedValue({ ...emptyMaster(), warehouses: ['A'], locations })
  const wrapper = mount(Workspace, { props: { factoryId: 'huaxing', customers: [] } })
  await flushPromises()
  expect(wrapper.find('[aria-label="修改仓库 A"]').exists()).toBe(false)
  get.mockResolvedValue({ ...emptyMaster(), can_manage: true, locations })
  await wrapper.findAll('button').find(b => b.text() === '刷新资料')!.trigger('click'); await flushPromises()
  await wrapper.get('[aria-label="修改仓库 A"]').trigger('click')
  await wrapper.findAll('button').find(b => b.text() === '删除仓库')!.trigger('click')
  get.mockResolvedValue(emptyMaster())
  await wrapper.setProps({ factoryId: 'huadeng' }); await flushPromises()
  expect(wrapper.find('form[aria-label="维护仓库"]').exists()).toBe(false)
  wrapper.unmount(); vi.restoreAllMocks()
})
