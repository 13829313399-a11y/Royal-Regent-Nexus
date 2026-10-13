import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createRouter, createMemoryHistory, RouterView, type Router } from 'vue-router'
import { cuttingOperationsRoutes } from '../routes'
import { cuttingApi, type MasterPage, type MasterRecord } from '../api'

vi.mock('@/components/layout/AccountMenu.vue', () => ({ default: { template: '<span />' } }))
vi.mock('../api', async original => ({
  ...await original<typeof import('../api')>(),
  cuttingApi: { access: vi.fn(), list: vi.fn(), save: vi.fn(), state: vi.fn(), versions: vi.fn() },
}))
const master = '/modules/production/cutting/master?factory=huakang-c'
const planning = '/modules/production/cutting/planning?factory=huakang-c'
const record: MasterRecord = {
  id: 'material-1', kind: 'material', factory_id: 'huakang-c', code: 'M01', version: 1, status: 'active',
  data: { name: '测试布料', category: 'fabric', unit: '米', color: '', specification: '', source_reference: '工程-M01' },
  actor_id: 'synthetic', created_at: '2026-10-08T00:00:00Z', reason: '测试',
}
const page = (data: MasterRecord[] = [], number = 1, total = data.length): MasterPage => ({ data, total, page: number, page_size: 50 })
function deferred<T>() {
  let resolve!: (value: T) => void, reject!: (error: Error) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}
let wrapper: VueWrapper, router: Router
beforeEach(async () => {
  vi.resetAllMocks()
  vi.spyOn(window, 'confirm').mockReturnValue(false)
  vi.mocked(cuttingApi.access).mockResolvedValue({ enabled: true, schema_ready: true, permissions: ['read', 'master_write', 'bom_write', 'bom_publish'] })
  vi.mocked(cuttingApi.list).mockResolvedValue(page())
  router = createRouter({ history: createMemoryHistory(), routes: [
    ...cuttingOperationsRoutes,
    { path: '/modules/production', component: { template: '<div>生产部</div>' } },
  ] })
  await router.push(master); await router.isReady()
  wrapper = mount(RouterView, { global: { plugins: [router] } })
  await flushPromises()
})
afterEach(() => { wrapper?.unmount(); vi.restoreAllMocks() })
function button(text: string) {
  const found = wrapper.findAll('button').find(b => b.text() === text)
  if (!found) throw new Error(`Missing button: ${text}`)
  return found
}
function field(text: string) {
  const found = wrapper.get('form.cutting-master-form').findAll('label').find(l => l.text() === text)
  if (!found) throw new Error(`Missing field: ${text}`)
  return found.get('input')
}
async function materialForm() {
  await button('物料与单位').trigger('click'); await flushPromises()
  await button('新增资料').trigger('click')
  await field('资料编码').setValue('M01'); await field('物料名称').setValue('测试布料')
  await field('基本单位').setValue('米'); await field('权威物料编码／资料来源').setValue('工程-M01')
  await field('登记／修订原因').setValue('测试')
}
function unload() {
  const event = new Event('beforeunload', { cancelable: true })
  window.dispatchEvent(event)
  return event.defaultPrevented
}
const options = () => wrapper.get('select[aria-label="选择物料版本"]')

describe('cutting master edit and navigation protection', () => {
  it('preserves a dirty BOM when category discard is cancelled, and switches on confirmation', async () => {
    await button('新增资料').trigger('click'); await field('产品名称').setValue('保留此产品')
    await button('物料与单位').trigger('click'); await flushPromises()
    expect(window.confirm).toHaveBeenCalledOnce()
    expect(field('产品名称').element.value).toBe('保留此产品')
    expect(cuttingApi.save).not.toHaveBeenCalled()
    vi.mocked(window.confirm).mockReturnValue(true)
    await button('物料与单位').trigger('click'); await flushPromises()
    expect(wrapper.find('form.cutting-master-form').exists()).toBe(false)
    expect(cuttingApi.list).toHaveBeenLastCalledWith('material', 1, '')
  })
  it('protects nested BOM edits from cancel and replacement, without prompting for unchanged forms', async () => {
    await button('新增资料').trigger('click'); await button('取消').trigger('click')
    expect(window.confirm).not.toHaveBeenCalled()
    await button('新增资料').trigger('click'); await button('添加部件').trigger('click')
    await field('部件名称').setValue('前片')
    await button('取消').trigger('click'); await button('新增资料').trigger('click')
    expect(window.confirm).toHaveBeenCalledTimes(2)
    expect(field('部件名称').element.value).toBe('前片')
    vi.mocked(window.confirm).mockReturnValue(true)
    await button('取消').trigger('click')
    expect(wrapper.find('form.cutting-master-form').exists()).toBe(false)
    expect(unload()).toBe(false)
  })
  it('guards route leaving and browser reload, then releases guards after confirmed discard', async () => {
    await materialForm()
    expect(unload()).toBe(true)
    await router.push(planning); await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe(master)
    expect(field('物料名称').element.value).toBe('测试布料')
    vi.mocked(window.confirm).mockReturnValue(true)
    await router.push(planning); await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe(planning)
    expect(unload()).toBe(false)
  })
  it('protects edits when an invalid factory query redirects away from the workspace', async () => {
    await materialForm()
    await router.push('/modules/production/cutting/master?factory=huaxing'); await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe(master)
    expect(field('物料名称').element.value).toBe('测试布料')
  })
  it('blocks leaving during an in-flight save and after timeout; retry uses the same operation', async () => {
    const save = deferred<MasterRecord>()
    vi.mocked(cuttingApi.save).mockReturnValueOnce(save.promise).mockResolvedValueOnce(record)
    await materialForm()
    await wrapper.get('form.cutting-master-form').trigger('submit')
    await router.push(planning); await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe(master)
    expect(wrapper.text()).toContain('正在保存，请等待结果')
    expect(unload()).toBe(true)
    save.reject(new Error('timeout')); await flushPromises()
    const original = vi.mocked(cuttingApi.save).mock.calls[0]
    vi.mocked(window.confirm).mockReturnValue(true)
    await router.push(planning); await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe(master)
    expect(window.confirm).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('重试原操作')
    expect(unload()).toBe(true)
    await button('重试原操作').trigger('click'); await flushPromises()
    expect(vi.mocked(cuttingApi.save).mock.calls[1]).toEqual(original)
    expect(cuttingApi.save).toHaveBeenCalledTimes(2)
    expect(unload()).toBe(false)
    await router.push(planning); await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe(planning)
  })
  it('protects draft edits before opening a state change and retains uncertain state retries', async () => {
    vi.mocked(cuttingApi.list).mockResolvedValue(page([record]))
    await materialForm()
    await button('停用').trigger('click')
    expect(field('物料名称').element.value).toBe('测试布料')
    expect(wrapper.text()).not.toContain('确认变更资料状态')
    vi.mocked(window.confirm).mockReturnValue(true)
    await button('停用').trigger('click')
    await field('核对依据／原因').setValue('停止使用')
    vi.mocked(window.confirm).mockReturnValue(false)
    await button('取消').trigger('click')
    expect(field('核对依据／原因').element.value).toBe('停止使用')
    vi.mocked(cuttingApi.state).mockRejectedValueOnce(new Error('timeout')).mockResolvedValueOnce({ ...record, status: 'inactive', version: 2 })
    await wrapper.get('form.cutting-master-form').trigger('submit'); await flushPromises()
    const original = vi.mocked(cuttingApi.state).mock.calls[0]
    await router.push(planning); await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe(master)
    await button('重试原操作').trigger('click'); await flushPromises()
    expect(vi.mocked(cuttingApi.state).mock.calls[1]).toEqual(original)
    expect(unload()).toBe(false)
  })
  it.each([401, 403, 409])('retains an uncertain operation after a retry returns HTTP %i', async status => {
    vi.mocked(cuttingApi.save).mockRejectedValueOnce(new Error('timeout'))
      .mockRejectedValueOnce({ response: { status, data: { detail: '重试未被受理' } } })
      .mockResolvedValueOnce(record)
    await materialForm()
    await wrapper.get('form.cutting-master-form').trigger('submit'); await flushPromises()
    const original = vi.mocked(cuttingApi.save).mock.calls[0]
    await button('重试原操作').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('保存结果尚未确认')
    expect(button('重试原操作').exists()).toBe(true)
    if (status === 401) expect(wrapper.get('a[target="_blank"]').attributes('href')).toBe('/login')
    expect(unload()).toBe(true)
    await router.push(planning); await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe(master)
    await button('重试原操作').trigger('click'); await flushPromises()
    expect(vi.mocked(cuttingApi.save).mock.calls[2]).toEqual(original)
    expect(wrapper.text()).toContain('已保存 M01')
    expect(unload()).toBe(false)
  })
  it('allows leaving after an initial definitive rejection without keeping a false pending operation', async () => {
    vi.mocked(cuttingApi.save).mockRejectedValue({ response: { status: 403 } })
    await materialForm()
    await wrapper.get('form.cutting-master-form').trigger('submit'); await flushPromises()
    expect(wrapper.text()).not.toContain('重试原操作')
    expect(unload()).toBe(false)
    await router.push(planning); await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe(planning)
  })
})

describe('cutting material lookup ordering', () => {
  beforeEach(async () => { await button('新增资料').trigger('click') })
  it('keeps the newest search when the earlier response arrives last', async () => {
    const first = deferred<MasterPage>(), second = deferred<MasterPage>()
    vi.mocked(cuttingApi.list).mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    await field('按物料编码查询').setValue('A'); await button('查询物料').trigger('click')
    await field('按物料编码查询').setValue('B'); await button('查询物料').trigger('click')
    second.resolve(page([{ ...record, id: 'B', code: 'B' }])); await flushPromises()
    await options().setValue('B')
    first.resolve(page([{ ...record, id: 'A', code: 'A' }])); await flushPromises()
    expect(options().text()).toContain('B · 测试布料')
    expect(options().text()).not.toContain('A · 测试布料')
    await button('加入 BOM').trigger('click')
    vi.mocked(cuttingApi.save).mockResolvedValue(record)
    await wrapper.get('form.cutting-master-form').trigger('submit'); await flushPromises()
    expect(vi.mocked(cuttingApi.save).mock.calls[0]![0].data).toMatchObject({ requirements: [expect.objectContaining({ material_id: 'B' })] })
  })
  it('ignores an earlier failed query after a newer query succeeds', async () => {
    const first = deferred<MasterPage>()
    vi.mocked(cuttingApi.list).mockReturnValueOnce(first.promise).mockResolvedValueOnce(page([record]))
    await button('查询物料').trigger('click'); await button('查询物料').trigger('click'); await flushPromises()
    first.reject(new Error('old failure')); await flushPromises()
    expect(options().text()).toContain('M01 · 测试布料')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })
  it('clears selectable results immediately when query text changes, including late responses', async () => {
    vi.mocked(cuttingApi.list).mockResolvedValueOnce(page([record]))
    await button('查询物料').trigger('click'); await flushPromises(); await options().setValue(record.id)
    await field('按物料编码查询').setValue('new query')
    expect(options().findAll('option')).toHaveLength(1)
    expect(button('加入 BOM').attributes('disabled')).toBeDefined()
    const old = deferred<MasterPage>()
    vi.mocked(cuttingApi.list).mockReturnValueOnce(old.promise)
    await button('查询物料').trigger('click'); await field('按物料编码查询').setValue('another query')
    old.resolve(page([record])); await flushPromises()
    expect(options().findAll('option')).toHaveLength(1)
  })
  it('ignores an old lookup after opening a different editor, even with identical query text', async () => {
    const old = deferred<MasterPage>()
    vi.mocked(cuttingApi.list).mockReturnValueOnce(old.promise)
    await button('查询物料').trigger('click'); await button('新增资料').trigger('click')
    old.resolve(page([record])); await flushPromises()
    expect(options().findAll('option')).toHaveLength(1)
    expect(window.confirm).not.toHaveBeenCalled()
  })
  it('loads the requested result page while invalidating the previous selection', async () => {
    vi.mocked(cuttingApi.list).mockResolvedValueOnce(page([record], 1, 51)).mockResolvedValueOnce(page([{ ...record, id: 'page-2', code: 'M51' }], 2, 51))
    await button('查询物料').trigger('click'); await flushPromises(); await options().setValue(record.id)
    await button('下一批物料').trigger('click'); await flushPromises()
    expect(cuttingApi.list).toHaveBeenLastCalledWith('material', 2, '')
    expect(options().text()).toContain('M51 · 测试布料')
    expect(button('加入 BOM').attributes('disabled')).toBeDefined()
    expect(button('上一批物料').exists()).toBe(true)
  })
})
