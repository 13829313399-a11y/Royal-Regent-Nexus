vi.mock('../CartonCustomerResponsibilities.vue', () => ({ default: { template: '<div />' } }))
import { mount, flushPromises } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import Assist from '../CartonMasterOrderAssist.vue'
import Lookup from '../CartonMasterLookup.vue'
import Workspace from '../CartonMasterWorkspace.vue'
import Settings from '../CartonMasterSettings.vue'
import { http } from '@/lib/http'
import { cartonMasterApi, defaultMasterData, emptyMaster, masterDueRules, historicalNumberSamples, numberWarning, type MasterRecord } from '@/api/cartonMaster'

vi.mock('@/lib/http', async importOriginal => ({ ...await importOriginal<typeof import('@/lib/http')>(), http: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }))
const record = (id: string, customer = '360', count = '120'): MasterRecord => ({
  id, kind: 'CONFIG', customer_code: customer, code: '00123', status: 'ACTIVE', revision: 1,
  preferred: false, maintained: false, updated_at: '', sources: [],
  data: { ...defaultMasterData(), product_name: '消防车', lines: [
    { packaging_type: '外箱', paper_quality: 'A33', specification: '30*20*15', dimension_unit: 'cm', unit: '个', usage_quantity: count },
    { packaging_type: '滑板纸', paper_quality: 'A33', specification: '30*20', dimension_unit: 'cm', unit: '张', usage_quantity: count },
  ] },
})

it('sends master import files as multipart and includes the confirmed preview token', async () => {
  vi.mocked(http.post).mockResolvedValue({ data: { added: 1 } })
  const file = new File(['xlsx'], '资料.xlsx')
  await cartonMasterApi.importPreview('huaxing', 'paper-options', file)
  await cartonMasterApi.importApply('huaxing', 'configurations', file, 'confirmed-token')
  const calls = vi.mocked(http.post).mock.calls.slice(-2)
  expect(calls[0]![0]).toContain('/paper-options/preview')
  expect(calls[1]![0]).toContain('/configurations/apply')
  for (const call of calls) {
    expect(call[1]).toBeInstanceOf(FormData)
    expect((call[1] as FormData).get('file')).toBe(file)
    expect((call[1] as FormData).get('factory_id')).toBe('huaxing')
    expect(call[2]).toEqual({ headers: { 'Content-Type': 'multipart/form-data' } })
  }
  expect((calls[1]![1] as FormData).get('preview_token')).toBe('confirmed-token')
})

it.each(['下载纸品选项模板', '下载仓位模板'])('shows backend JSON Blob detail when %s downloading fails', async label => {
  const get = vi.spyOn(cartonMasterApi, 'get').mockResolvedValue({ ...emptyMaster(), can_manage: true })
  const body = new Blob([JSON.stringify({ detail: '当前厂区无模板下载权限' })], { type: 'application/json' })
  const download = vi.spyOn(cartonMasterApi, 'template').mockRejectedValue({ isAxiosError: true, message: 'Request failed with status code 403', response: { data: body } })
  const wrapper = mount(Workspace, { props: { factoryId: 'huaxing', customers: [] } })
  await flushPromises()
  await wrapper.findAll('button').find(button => button.text() === label)!.trigger('click')
  await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toBe('模板下载失败：当前厂区无模板下载权限')
  expect(download).toHaveBeenCalledWith('huaxing', label === '下载仓位模板' ? 'locations' : 'paper-options')
  wrapper.unmount(); download.mockRestore(); get.mockRestore()
})

it('discards template download errors when factory changes during Blob parsing', async () => {
  const get = vi.spyOn(cartonMasterApi, 'get').mockResolvedValue({ ...emptyMaster(), can_manage: true })
  let finishParsing!: (value: string) => void
  const body = new Blob([], { type: 'application/json' })
  const parse = vi.fn(() => new Promise<string>(resolve => { finishParsing = resolve }))
  Object.defineProperty(body, 'text', { value: parse })
  const download = vi.spyOn(cartonMasterApi, 'template').mockRejectedValue({ isAxiosError: true, message: 'Request failed', response: { data: body } })
  const wrapper = mount(Workspace, { props: { factoryId: 'huaxing', customers: [] } })
  await flushPromises()
  await wrapper.findAll('button').find(button => button.text() === '下载纸品选项模板')!.trigger('click')
  await flushPromises()
  expect(parse).toHaveBeenCalledOnce()
  await wrapper.setProps({ factoryId: 'huadeng' }); await flushPromises()
  finishParsing(JSON.stringify({ detail: '旧厂区下载错误' })); await flushPromises()
  expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  expect(wrapper.text()).not.toContain('旧厂区下载错误')
  wrapper.unmount(); download.mockRestore(); get.mockRestore()
})

it('keeps a pending template download failure visible inside the import dialog', async () => {
  const get = vi.spyOn(cartonMasterApi, 'get').mockResolvedValue({ ...emptyMaster(), can_manage: true })
  let rejectDownload!: (reason: unknown) => void
  const download = vi.spyOn(cartonMasterApi, 'template').mockImplementation(() => new Promise<Blob>((_, reject) => { rejectDownload = reject }))
  const wrapper = mount(Workspace, { props: { factoryId: 'huaxing', customers: [] } })
  try {
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '下载纸品选项模板')!.trigger('click')
    await wrapper.findAll('button').find(button => button.text() === '导入纸品选项')!.trigger('click')
    rejectDownload({ isAxiosError: true, message: 'Request failed', response: { status: 403, data: { detail: '当前账号不可下载此模板' } } })
    await flushPromises()
    expect(wrapper.get('[role="dialog"]').get('[role="alert"]').text()).toBe('模板下载失败：当前账号不可下载此模板')
  } finally { wrapper.unmount(); download.mockRestore(); get.mockRestore() }
})

it('keeps a completed master import locked and explains its refresh failure in the dialog', async () => {
  const result = { factory_id: 'huaxing', kind: 'paper-options' as const, fingerprint: 'file', master_revision: 'revision', preview_token: 'token', added: 1, skipped: 0, errors: [] as string[], details: [] }
  const get = vi.spyOn(cartonMasterApi, 'get').mockResolvedValue({ ...emptyMaster(), can_manage: true })
  const preview = vi.spyOn(cartonMasterApi, 'importPreview').mockResolvedValue(result)
  const apply = vi.spyOn(cartonMasterApi, 'importApply').mockResolvedValue(result)
  const wrapper = mount(Workspace, { props: { factoryId: 'huaxing', customers: [] } })
  try {
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '导入纸品选项')!.trigger('click')
    const input = wrapper.get<HTMLInputElement>('[aria-label="选择基础资料模板文件"]')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [new File(['xlsx'], '资料.xlsx')] })
    await input.trigger('change')
    await wrapper.findAll('button').find(button => button.text() === '预览导入')!.trigger('click'); await flushPromises()
    get.mockRejectedValueOnce(new Error('资料读取暂不可用'))
    await wrapper.findAll('button').find(button => button.text() === '确认导入')!.trigger('click'); await flushPromises()
    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.text()).toContain('导入完成')
    expect(dialog.get('[role="alert"]').text()).toContain('基础资料已导入，但列表刷新失败：资料读取暂不可用')
    expect(dialog.findAll('button').some(button => button.text() === '确认导入')).toBe(false)
    expect(apply).toHaveBeenCalledTimes(1)
  } finally { wrapper.unmount(); get.mockRestore(); preview.mockRestore(); apply.mockRestore() }
})

it.each(['paper-options', 'configurations', 'locations'] as const)('previews and confirms %s imports, retaining dialog until explicit close', async kind => {
  const result = { factory_id: 'huaxing', kind, fingerprint: 'file', master_revision: 'revision', preview_token: 'token', added: 2, skipped: 1, errors: [] as string[], details: ['待新增配置'] }
  const get = vi.spyOn(cartonMasterApi, 'get').mockResolvedValue({ ...emptyMaster(), can_manage: true })
  const preview = vi.spyOn(cartonMasterApi, 'importPreview').mockResolvedValue(result)
  const apply = vi.spyOn(cartonMasterApi, 'importApply').mockResolvedValue(result)
  const wrapper = mount(Workspace, { props: { factoryId: 'huaxing', customers: [], initialTab: kind === 'configurations' ? 'CONFIG' : 'SETTINGS' } })
  await flushPromises()
  const click = async (label: string) => { await wrapper.findAll('button').find(b => b.text() === label)!.trigger('click'); await flushPromises() }
  const labels = { 'paper-options': ['下载纸品选项模板', '导入纸品选项'], configurations: ['下载货号包装模板', '导入货号与包装'], locations: ['下载仓位模板', '导入仓库仓位'] }
  expect(wrapper.text()).toContain(labels[kind][0])
  await click(labels[kind][1]!)
  expect(wrapper.get('[role="dialog"]').text()).toContain('至少一行')
  if (kind === 'locations') {
    expect(wrapper.get('[role="dialog"]').text()).toContain('A1-A25、B01-B03')
    expect(wrapper.get('[role="dialog"]').text()).not.toContain('规格分别填写长')
  }
  if (kind === 'configurations') {
    expect(wrapper.text()).toContain('一个货号可以有多个纸品')
    expect(wrapper.get('[role="dialog"]').text()).toContain('每个纸品写一行')
    expect(wrapper.get('[role="dialog"]').text()).toContain('货号 + 配置组')
  }
  expect(wrapper.findAll('button').find(b => b.text() === '确认导入')!.attributes('disabled')).toBeDefined()
  const input = wrapper.get<HTMLInputElement>('[aria-label="选择基础资料模板文件"]')
  const file = new File(['xlsx'], '资料.xlsx')
  Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
  await input.trigger('change')
  await click('预览导入')
  expect(preview).toHaveBeenCalledWith('huaxing', kind, file)
  expect(wrapper.text()).toContain('资料.xlsx')
  expect(wrapper.text()).toContain('待新增 2 · 跳过 1 · 错误 0')
  if (kind === 'locations') expect(wrapper.text()).toContain('按展开后的仓位数统计')
  expect(apply).not.toHaveBeenCalled()
  await wrapper.get('[data-testid="master-import-backdrop"]').trigger('click')
  expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
  await click('确认导入')
  expect(apply).toHaveBeenCalledWith('huaxing', kind, file, 'token')
  expect(get).toHaveBeenCalledTimes(2)
  expect(wrapper.emitted('changed')).toHaveLength(1)
  expect(wrapper.text()).toContain('导入完成')
  expect(wrapper.findAll('button').some(b => b.text() === '确认导入')).toBe(false)
  wrapper.unmount(); get.mockRestore(); preview.mockRestore(); apply.mockRestore()
})

it('shows import row errors, invalidates previews on file change and closes on factory switch', async () => {
  const get = vi.spyOn(cartonMasterApi, 'get').mockResolvedValue({ ...emptyMaster(), can_manage: true })
  const preview = vi.spyOn(cartonMasterApi, 'importPreview').mockResolvedValue({ factory_id: 'huaxing', kind: 'paper-options', fingerprint: '', master_revision: '', preview_token: 'token', added: 1, skipped: 0, errors: ['第 3 行：长、宽、高必须全部填写'], details: [] })
  const wrapper = mount(Workspace, { props: { factoryId: 'huaxing', customers: [] } })
  await flushPromises()
  await wrapper.findAll('button').find(b => b.text() === '导入纸品选项')!.trigger('click')
  const input = wrapper.get<HTMLInputElement>('[aria-label="选择基础资料模板文件"]')
  Object.defineProperty(input.element, 'files', { configurable: true, value: [new File(['xlsx'], '资料.xlsx')] })
  await input.trigger('change')
  await wrapper.findAll('button').find(b => b.text() === '预览导入')!.trigger('click'); await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toContain('第 3 行')
  expect(wrapper.findAll('button').find(b => b.text() === '确认导入')!.attributes('disabled')).toBeDefined()
  await input.trigger('change')
  expect(wrapper.text()).not.toContain('预览结果')
  await wrapper.setProps({ factoryId: 'huadeng' }); await flushPromises()
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  wrapper.unmount(); get.mockRestore(); preview.mockRestore()
})

it('hides both template and import actions without master permission', async () => {
  const get = vi.spyOn(cartonMasterApi, 'get').mockResolvedValue(emptyMaster())
  const wrapper = mount(Workspace, { props: { factoryId: 'huaxing', customers: [] } })
  await flushPromises()
  expect(wrapper.text()).not.toContain('下载纸品选项模板')
  expect(wrapper.text()).not.toContain('导入纸品选项')
  expect(wrapper.text()).not.toContain('下载仓位模板')
  expect(wrapper.text()).not.toContain('导入仓库仓位')
  await wrapper.setProps({ initialTab: 'CONFIG' })
  expect(wrapper.text()).not.toContain('下载货号包装模板')
  expect(wrapper.text()).not.toContain('导入货号与包装')
  wrapper.unmount(); get.mockRestore()
})

describe('纸箱基础资料', () => {
  it.each(['', 'cm', 'mm', 'inch'])('defaults an unrecorded dimension unit to cm while retaining %s and loaded snapshots', async unit => {
    const config = record('CFG')
    config.data.lines![0]!.dimension_unit = unit
    const get = vi.spyOn(cartonMasterApi, 'get').mockResolvedValue({ ...emptyMaster(), can_manage: true, records: [config] })
    const save = vi.spyOn(cartonMasterApi, 'save').mockResolvedValue(config)
    const wrapper = mount(Workspace, { props: { factoryId: 'huaxing', customers: [], initialTab: 'CONFIG' } })
    await flushPromises()
    await wrapper.get('[aria-label="修改基础资料 00123"]').trigger('click')
    expect(wrapper.get<HTMLSelectElement>('[aria-label="资料尺寸单位"]').element.value).toBe(unit || 'cm')
    expect(config.data.lines![0]!.dimension_unit).toBe(unit)
    await wrapper.get('[aria-label="资料尺寸单位"]').element.closest('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()
    expect(save).toHaveBeenCalledWith('huaxing', expect.objectContaining({ data: expect.objectContaining({ lines: expect.arrayContaining([
      expect.objectContaining({ dimension_unit: unit || 'cm' }),
    ]) }) }), 'CFG')
    wrapper.unmount(); get.mockRestore(); save.mockRestore()
  })

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
    expect(wrapper.find('[aria-label="删除货号包装 00123"]').exists()).toBe(false)
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

it('confirms contract removal, preserves customer and provenance, and restores the original revision', async () => {
  let contract: MasterRecord = { ...record('CONTRACT'), kind: 'CONTRACT', code: 'SC123', data: { item_nos: ['00123'] }, sources: [{
    order_no: 'CT-HISTORY', order_date: '2026-09-01', contract_no: 'SC123', item_no: '00123', configuration: {},
  }] }
  const get = vi.spyOn(cartonMasterApi, 'get').mockImplementation(async () => ({ ...emptyMaster(), can_manage: true, records: [contract] }))
  const save = vi.spyOn(cartonMasterApi, 'save').mockImplementation(async (_factory, payload) => {
    contract = { ...contract, status: payload.status, revision: contract.revision + 1, maintained: true }
    return { ...contract, sources: [] }
  })
  const wrapper = mount(Workspace, { props: { factoryId: 'huaxing', customers: [{ id: 'C', customer_code: '360', customer_name: '360', status: 'ACTIVE' } as any] } })
  try {
    await flushPromises()
    await wrapper.get('[aria-label="删除关联合同 SC123"]').trigger('click')
    expect(save).not.toHaveBeenCalled()
    const dialog = wrapper.get('[role="dialog"][aria-label="删除关联合同"]')
    expect(dialog.text()).toContain('该客户不能再用此合同新增或确认订单')
    await dialog.findAll('button').find(b => b.text() === '取消')!.trigger('click')
    expect(save).not.toHaveBeenCalled()
    await wrapper.get('[aria-label="删除关联合同 SC123"]').trigger('click')
    await wrapper.get('[role="dialog"]').findAll('button').find(b => b.text() === '确认删除')!.trigger('click')
    await flushPromises()
    expect(save).toHaveBeenCalledWith('huaxing', expect.objectContaining({ kind: 'CONTRACT', customer_code: '360', status: 'INACTIVE', expected_revision: 1, data: expect.objectContaining({ item_nos: ['00123'] }) }), 'CONTRACT')
    expect(wrapper.find('[data-contract-id="CONTRACT"]').exists()).toBe(false)
    await wrapper.get('[aria-label="关联合同状态"]').setValue('INACTIVE')
    expect(wrapper.get('[data-contract-id="CONTRACT"]').text()).toContain('来源')
    await wrapper.get('[aria-label="恢复关联合同 SC123"]').trigger('click'); await flushPromises()
    expect(save).toHaveBeenLastCalledWith('huaxing', expect.objectContaining({ kind: 'CONTRACT', customer_code: '360', status: 'ACTIVE', expected_revision: 2 }), 'CONTRACT')
    await wrapper.get('[aria-label="关联合同状态"]').setValue('ACTIVE')
    expect(wrapper.get('[data-contract-id="CONTRACT"]').text()).toContain('启用')
    expect(contract.sources).toHaveLength(1)
  } finally { wrapper.unmount(); get.mockRestore(); save.mockRestore() }
})

it('does not show contract deletion or restore actions to read-only staff', async () => {
  const contract = { ...record('CONTRACT'), kind: 'CONTRACT', code: 'SC123', data: { item_nos: ['00123'] } } as MasterRecord
  const wrapper = mount(Settings, { props: { workspace: { ...emptyMaster(), records: [contract] }, customers: [{ id: 'C', customer_code: '360', customer_name: '360', status: 'ACTIVE' } as any] } })
  expect(wrapper.find('[aria-label="删除关联合同 SC123"]').exists()).toBe(false)
  await wrapper.setProps({ workspace: { ...emptyMaster(), records: [{ ...contract, status: 'INACTIVE' }] } })
  await wrapper.get('[aria-label="关联合同状态"]').setValue('INACTIVE')
  expect(wrapper.find('[aria-label="恢复关联合同 SC123"]').exists()).toBe(false)
  wrapper.unmount()
})

it('keeps a failed contract delete open and discards old-factory completion', async () => {
  const contract = { ...record('CONTRACT'), kind: 'CONTRACT', code: 'SC123', data: { item_nos: ['00123'] } } as MasterRecord
  const get = vi.spyOn(cartonMasterApi, 'get').mockImplementation(async factory => ({ ...emptyMaster(), can_manage: true, records: factory === 'huaxing' ? [contract] : [] }))
  let finish!: (row: MasterRecord) => void
  const save = vi.spyOn(cartonMasterApi, 'save').mockRejectedValueOnce(new Error('资料已更新，请刷新后重试')).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  const wrapper = mount(Workspace, { props: { factoryId: 'huaxing', customers: [{ id: 'C', customer_code: '360', customer_name: '360', status: 'ACTIVE' } as any] } })
  try {
    await flushPromises()
    await wrapper.get('[aria-label="删除关联合同 SC123"]').trigger('click')
    await wrapper.get('[role="dialog"]').findAll('button').find(b => b.text() === '确认删除')!.trigger('click'); await flushPromises()
    expect(wrapper.get('[role="dialog"] [role="alert"]').text()).toContain('资料已更新')
    await wrapper.get('[role="dialog"]').findAll('button').find(b => b.text() === '确认删除')!.trigger('click')
    await wrapper.setProps({ factoryId: 'huadeng' }); await flushPromises()
    finish({ ...contract, status: 'INACTIVE', revision: 2 }); await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('合同 SC123 已停用')
    expect(wrapper.emitted('changed')).toBeUndefined()
  } finally { wrapper.unmount(); get.mockRestore(); save.mockRestore() }
})

it('removes one packaging configuration from usable records and restores it without deleting history', async () => {
  let config: MasterRecord = { ...record('CFG'), preferred: true, sources: [{
    order_no: 'CT-HISTORY', order_date: '2026-09-01', contract_no: 'SC-OLD', item_no: '00123',
    customer_code: '360', configuration: {},
  }] }
  const get = vi.spyOn(cartonMasterApi, 'get').mockImplementation(async () => ({ ...emptyMaster(), can_manage: true, records: [config] }))
  const save = vi.spyOn(cartonMasterApi, 'save').mockImplementation(async (_factory, payload) => {
    config = { ...config, status: payload.status, preferred: payload.preferred, revision: config.revision + 1, maintained: true }
    return { ...config, sources: [] }
  })
  const wrapper = mount(Workspace, { props: { factoryId: 'huaxing', customers: [], initialTab: 'CONFIG' } })
  await flushPromises()
  expect(wrapper.get<HTMLSelectElement>('[aria-label="货号资料状态"]').element.value).toBe('ACTIVE')
  await wrapper.get('[data-config-id="CFG"] [aria-label="删除货号包装 00123"]').trigger('click')
  const dialog = wrapper.get('[role="dialog"][aria-label="删除货号与包装资料"]')
  expect(dialog.text()).toContain('历史订单及 1 条来源记录保留')
  expect(save).not.toHaveBeenCalled()
  await dialog.findAll('button').find(button => button.text() === '取消')!.trigger('click')
  expect(save).not.toHaveBeenCalled()

  await wrapper.get('[data-config-id="CFG"] [aria-label="删除货号包装 00123"]').trigger('click')
  await wrapper.get('[role="dialog"][aria-label="删除货号与包装资料"]').findAll('button').find(button => button.text() === '确认删除')!.trigger('click')
  await flushPromises()
  expect(save).toHaveBeenCalledWith('huaxing', expect.objectContaining({ kind: 'CONFIG', status: 'INACTIVE', preferred: false, expected_revision: 1, reason: '删除不再使用的货号包装资料' }), 'CFG')
  expect(wrapper.find('[data-config-id="CFG"]').exists()).toBe(false)
  expect(wrapper.get('[role="status"]').text()).toContain('可在“停用”中恢复')
  await wrapper.get('[aria-label="货号资料状态"]').setValue('INACTIVE')
  expect(wrapper.get('[data-config-id="CFG"]').text()).toContain('1 条历史来源')
  await wrapper.get('[data-config-id="CFG"] [aria-label="恢复货号包装 00123"]').trigger('click')
  await flushPromises()
  expect(save).toHaveBeenLastCalledWith('huaxing', expect.objectContaining({ status: 'ACTIVE', preferred: false, expected_revision: 2, reason: '恢复货号包装资料' }), 'CFG')
  expect(wrapper.get('[data-config-id="CFG"]').text()).toContain('启用')
  expect(config.sources).toHaveLength(1)
  wrapper.unmount(); get.mockRestore(); save.mockRestore()
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

it('defaults production to seven days and respects active factory/customer overrides including zero', () => {
  const factory = { ...record('F', ''), kind: 'RULE' as const, data: { production_days: 9 } }
  const customer = { ...record('C'), kind: 'RULE' as const, data: { production_days: 0 } }
  expect(masterDueRules([], '360').production_days).toBe(7)
  expect(masterDueRules([factory, customer], '360').production_days).toBe(0)
  expect(masterDueRules([factory, customer], 'OTHER').production_days).toBe(9)
  expect(masterDueRules([factory, { ...customer, status: 'INACTIVE' }], '360').production_days).toBe(9)
  expect(masterDueRules([factory, { ...customer, data: { production_days: null } }], '360').production_days).toBe(9)
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
  await wrapper.get('[aria-label="供应商生产送货周期"]').setValue('9')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(save).toHaveBeenCalledWith('huaxing', expect.objectContaining({ customer_code: '', expected_revision: 1, data: expect.objectContaining({ lead_days: 6, production_days: 9 }) }), 'FACTORY')
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
  const remove = vi.spyOn(cartonMasterApi, 'deleteWarehouse').mockRejectedValueOnce(new Error('该仓库已使用，不能删除')).mockResolvedValue({ deleted: true })
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
  expect(wrapper.find('[role="alert"]').text()).toBe('该仓库已使用，不能删除')
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


it('recognizes item and customer PO from contract provenance without a complete packaging CONFIG', () => {
  const contract: MasterRecord = { ...record('CONTRACT'), kind: 'CONTRACT', sources: [{
    order_no: 'HISTORY', order_date: '', contract_no: 'SC000000001/001', item_no: '000012345',
    customer_po: 'PO-000012', customer_code: '360', configuration: {},
  }] }
  const foreign = { ...contract, id: 'FOREIGN', customer_code: 'OTHER', sources: [{ ...contract.sources[0]!, customer_code: 'OTHER', item_no: 'WRONG', customer_po: 'WRONG' }] }
  expect(historicalNumberSamples([contract, contract, foreign], '360', 'item_rule')).toEqual(['000012345'])
  expect(historicalNumberSamples([contract, foreign], '360', 'customer_po_rule')).toEqual(['PO-000012'])
  expect(historicalNumberSamples([{ ...contract, sources: [{ ...contract.sources[0]!, customer_po: '' }] }], '360', 'customer_po_rule')).toEqual([])
})

it('keeps recognition errors on their own field and persists an explicit format reset', async () => {
  const contract: MasterRecord = { ...record('CONTRACT'), kind: 'CONTRACT', sources: [{
    order_no: 'HISTORY', order_date: '', contract_no: 'SC000000001/001', item_no: 'BAD ITEM',
    customer_po: 'PO-000012', customer_code: '360', configuration: {},
  }] }
  const get = vi.spyOn(cartonMasterApi, 'get').mockResolvedValue({ ...emptyMaster(), can_manage: true, records: [contract] })
  const save = vi.spyOn(cartonMasterApi, 'save').mockResolvedValue({ ...record('RULE'), kind: 'RULE' })
  const wrapper = mount(Workspace, { props: { factoryId: 'huaxing', customers: [{ id: 'C', customer_code: '360', customer_name: '360' } as any] } })
  await flushPromises()
  await wrapper.get('[aria-label="设置客户规则 360"]').trigger('click')
  expect(wrapper.get('[aria-label="货号格式检查方式"]').element.value).toBe('OFF')
  expect(wrapper.text()).not.toContain('货号识别失败')
  await wrapper.get('[aria-label="货号格式检查方式"]').setValue('AUTO')
  await wrapper.get('[aria-label="识别货号格式"]').trigger('click')
  expect(wrapper.text()).toContain('货号识别失败')
  expect(wrapper.get<HTMLTextAreaElement>('[aria-label="客户 PO（选填）固定格式"]').element.value).toBe('PO-{6}')
  await wrapper.get('[aria-label="删除旧货号格式"]').trigger('click')
  expect(wrapper.text()).not.toContain('货号识别失败')
  expect(wrapper.get('[aria-label="货号格式检查方式"]').element.value).toBe('OFF')
  expect(wrapper.find('[aria-label="货号固定格式"]').exists()).toBe(false)
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(save).toHaveBeenCalledTimes(2)
  expect(save.mock.calls[0]![1].data.customer_po_rule.templates).toEqual([])
  const saved = save.mock.calls[1]![1].data
  expect(saved.item_rule.reset).toBe(true)
  expect(saved.item_rule.templates).toEqual([])
  expect(saved.customer_po_rule.templates).toEqual(['PO-{6}'])
  get.mockResolvedValue({ ...emptyMaster(), can_manage: true, records: [contract, { ...record('RULE'), kind: 'RULE', data: saved }] })
  await wrapper.findAll('button').find(button => button.text() === '刷新资料')!.trigger('click'); await flushPromises()
  await wrapper.get('[aria-label="设置客户规则 360"]').trigger('click')
  expect(wrapper.get('[aria-label="货号格式检查方式"]').element.value).toBe('OFF')
  expect(wrapper.text()).not.toContain('货号识别失败')
  wrapper.unmount(); get.mockRestore(); save.mockRestore()
})

it('defaults item formats to OFF, preserves manual checks, and records explicit opt-in', async () => {
  const old = { ...defaultMasterData(), item_rule: { ...defaultMasterData().contract_rule,
    templates: ['{9}'], frozen: true, source: 'HISTORY' as const } }
  const rule: MasterRecord = { ...record('RULE'), kind: 'RULE', code: '', data: old }
  expect(defaultMasterData().item_rule.mode).toBe('OFF')
  expect(masterDueRules([rule], '360').item_rule.mode).toBe('OFF')
  expect(masterDueRules([{ ...rule, data: { ...old, item_rule: { ...old.item_rule, source: 'MANUAL' } } }], '360').item_rule.mode).toBe('AUTO')
  expect(masterDueRules([{ ...rule, data: { ...old, item_rule: { ...old.item_rule, mode: 'BLOCK' } } }], '360').item_rule.mode).toBe('BLOCK')
  const get = vi.spyOn(cartonMasterApi, 'get').mockResolvedValue({ ...emptyMaster(), can_manage: true, records: [rule] })
  const save = vi.spyOn(cartonMasterApi, 'save').mockResolvedValue(rule)
  const wrapper = mount(Workspace, { props: { factoryId: 'huaxing', customers: [{ id: 'C', customer_code: '360', customer_name: '360' } as any] } })
  try {
    await flushPromises()
    await wrapper.get('[aria-label="设置客户规则 360"]').trigger('click')
    expect(wrapper.get('[aria-label="货号格式检查方式"]').element.value).toBe('OFF')
    await wrapper.get('[aria-label="货号格式检查方式"]').setValue('AUTO')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(save.mock.calls[0]![1].data.item_rule).toMatchObject({ mode: 'AUTO', user_configured: true, templates: ['{9}'] })
  } finally { wrapper.unmount(); get.mockRestore(); save.mockRestore() }
})

it('deletes a saved contract format immediately without restoring old order samples', async () => {
  const old = { ...defaultMasterData(), lead_days: 6, contract_rule: {
    ...defaultMasterData().contract_rule, templates: ['OLD{5}'], frozen: true, sample_text: 'OLD00001', source: 'MANUAL' as const,
  } }
  const rule: MasterRecord = { ...record('RULE'), kind: 'RULE', code: '', data: old }
  const history: MasterRecord = { ...record('H'), kind: 'CONTRACT', sources: [{
    order_no: 'O1', order_date: '', contract_no: 'OLD00001', item_no: '203307004', configuration: {},
  }] }
  const get = vi.spyOn(cartonMasterApi, 'get').mockResolvedValue({ ...emptyMaster(), can_manage: true, records: [rule, history] })
  const saved: MasterRecord = { ...rule, revision: 2, data: { ...old, contract_rule: { ...defaultMasterData().contract_rule, reset: true } } }
  const save = vi.spyOn(cartonMasterApi, 'save').mockResolvedValue(saved)
  const wrapper = mount(Workspace, { props: { factoryId: 'huaxing', customers: [{ id: 'C', customer_code: '360', customer_name: '360' } as any] } })
  await flushPromises()
  await wrapper.get('[aria-label="设置客户规则 360"]').trigger('click')
  await wrapper.get('[aria-label="删除旧合同号格式"]').trigger('click'); await flushPromises()
  expect(save).toHaveBeenCalledOnce()
  expect(save).toHaveBeenCalledWith('huaxing', expect.objectContaining({
    expected_revision: 1, data: expect.objectContaining({ lead_days: 6, contract_rule: expect.objectContaining({ templates: [], reset: true }) }),
  }), 'RULE')
  expect(wrapper.get<HTMLTextAreaElement>('[aria-label="合同号固定格式"]').element.value).toBe('')
  await wrapper.get('[aria-label="识别合同号格式"]').trigger('click')
  expect(wrapper.get<HTMLTextAreaElement>('[aria-label="合同号固定格式"]').element.value).toBe('')
  expect(wrapper.text()).toContain('旧格式已删除')
  wrapper.unmount(); get.mockRestore(); save.mockRestore()
})

it('persists deletion when a customer has history but no saved rule', async () => {
  const history: MasterRecord = { ...record('H'), kind: 'CONTRACT', sources: [{
    order_no: 'O1', order_date: '', contract_no: 'OLD00001', item_no: '203307004', configuration: {},
  }] }
  const cleared: MasterRecord = { ...record('NEW-RULE'), kind: 'RULE', code: '', data: {
    ...defaultMasterData(), contract_rule: { ...defaultMasterData().contract_rule, reset: true },
  } }
  const get = vi.spyOn(cartonMasterApi, 'get').mockResolvedValueOnce({ ...emptyMaster(), can_manage: true, records: [history] })
    .mockResolvedValue({ ...emptyMaster(), can_manage: true, records: [history, cleared] })
  const save = vi.spyOn(cartonMasterApi, 'save').mockResolvedValue(cleared)
  const wrapper = mount(Workspace, { props: { factoryId: 'huaxing', customers: [{ id: 'C', customer_code: '360', customer_name: '360' } as any] } })
  await flushPromises()
  await wrapper.get('[aria-label="设置客户规则 360"]').trigger('click')
  expect(wrapper.get<HTMLTextAreaElement>('[aria-label="合同号固定格式"]').element.value).toBe('OLD{5}')
  await wrapper.get('[aria-label="删除旧合同号格式"]').trigger('click'); await flushPromises()
  expect(save).toHaveBeenCalledWith('huaxing', expect.objectContaining({
    customer_code: '360', expected_revision: 0,
    data: expect.objectContaining({ contract_rule: expect.objectContaining({ templates: [], reset: true }) }),
  }), '')
  await wrapper.get('[aria-label="关闭基础资料编辑"]').trigger('click')
  await wrapper.findAll('button').find(button => button.text() === '刷新资料')!.trigger('click'); await flushPromises()
  await wrapper.get('[aria-label="设置客户规则 360"]').trigger('click')
  expect(wrapper.get<HTMLTextAreaElement>('[aria-label="合同号固定格式"]').element.value).toBe('')
  wrapper.unmount(); get.mockRestore(); save.mockRestore()
})


it('maintains independent paper weights and keeps historical header values separate', async () => {
  const source = record('WEIGHTS')
  source.data.net_weight_kg = '77'
  source.data.gross_weight_kg = '88'
  source.data.lines![0]!.net_weight_kg = '8.125'
  source.data.lines![0]!.gross_weight_kg = '9.25'
  const original = JSON.stringify(source)
  const get = vi.spyOn(cartonMasterApi, 'get').mockResolvedValue({ ...emptyMaster(), can_manage: true, records: [source] })
  const save = vi.spyOn(cartonMasterApi, 'save').mockResolvedValue(source)
  const wrapper = mount(Workspace, { props: { factoryId: 'huaxing', customers: [], initialTab: 'CONFIG' } })
  try {
    await flushPromises()
    await wrapper.get('[aria-label="修改基础资料 00123"]').trigger('click')
    const form = wrapper.get('form')
    expect(form.text()).toContain('历史整单每箱净重 77')
    expect(form.find('[aria-label="基础资料每箱净重"]').exists()).toBe(false)
    expect(form.get<HTMLInputElement>('[aria-label="资料纸品每箱净重 1"]').element.value).toBe('8.125')
    expect(form.get<HTMLInputElement>('[aria-label="资料纸品每箱净重 2"]').element.value).toBe('')
    await form.get('[aria-label="资料纸品每箱净重 2"]').setValue('0.4')
    await form.get('[aria-label="资料纸品每箱毛重 2"]').setValue('0.3')
    await form.trigger('submit'); await flushPromises()
    expect(save).not.toHaveBeenCalled()
    expect(form.text()).toContain('第 2 条纸品重量无效')
    await form.get('[aria-label="资料纸品每箱毛重 2"]').setValue('0.5')
    await form.trigger('submit'); await flushPromises()
    expect(save).toHaveBeenCalledWith('huaxing', expect.objectContaining({ data: expect.objectContaining({
      net_weight_kg: '77', gross_weight_kg: '88', lines: [
        expect.objectContaining({ net_weight_kg: 8.125, gross_weight_kg: 9.25 }),
        expect.objectContaining({ net_weight_kg: 0.4, gross_weight_kg: 0.5 }),
      ],
    }) }), 'WEIGHTS')
    expect(JSON.stringify(source)).toBe(original)
  } finally { wrapper.unmount(); get.mockRestore(); save.mockRestore() }
})
